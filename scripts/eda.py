"""Exploratory plots for a data JSONL file: length distributions and a coverage heatmap."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

from scripts.validate_data import CLASSES, SOURCES, SURFACES, row_class  # noqa: E402
from training.jsonl import read_rows  # noqa: E402
from training.schemas import DataRow  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "docs" / "figures"


def to_frame(rows: list[DataRow]) -> pd.DataFrame:
    """One row per item with the columns the plots need."""
    return pd.DataFrame({
        "class": [row_class(r) for r in rows],
        "label": [r.label for r in rows],
        "surface": [r.surface for r in rows],
        "source": [r.source for r in rows],
        "chars": [len(r.text) for r in rows],
    })


def plot_lengths(df: pd.DataFrame, path: Path) -> None:
    """Character-length histogram by label and box plot by surface."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    sns.histplot(data=df, x="chars", hue="label", bins=30, ax=axes[0])
    axes[0].set_title("Text length by label")
    sns.boxplot(data=df, x="surface", y="chars", order=SURFACES, ax=axes[1])
    axes[1].set_title("Text length by surface")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_coverage(df: pd.DataFrame, path: Path) -> None:
    """Heatmap of row counts per class x surface/source cell."""
    cols = [f"{s}/{src}" for s in SURFACES for src in SOURCES]
    df = df.assign(cell=df["surface"] + "/" + df["source"])
    table = (df.groupby(["class", "cell"]).size().unstack(fill_value=0)
             .reindex(index=CLASSES, columns=cols, fill_value=0))
    fig, ax = plt.subplots(figsize=(12, 4.5))
    sns.heatmap(table, annot=True, fmt="d", cmap="Blues", cbar=False, linewidths=0.5, ax=ax)
    ax.set_title("Coverage: rows per class x surface/source (0 = empty cell)")
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; writes <name>_lengths.png and <name>_coverage.png."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=Path)
    p.add_argument("--name", help="file prefix; default is the input file stem")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args(argv)

    rows, errors = read_rows(args.path)
    if errors or not rows:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print("fix the file with scripts/validate_data.py first", file=sys.stderr)
        return 1
    name = args.name or args.path.stem
    args.out.mkdir(parents=True, exist_ok=True)
    df = to_frame(rows)
    plot_lengths(df, args.out / f"{name}_lengths.png")
    plot_coverage(df, args.out / f"{name}_coverage.png")
    print(f"wrote {name}_lengths.png and {name}_coverage.png to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
