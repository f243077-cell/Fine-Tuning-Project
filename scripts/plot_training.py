"""Loss and val-metric curves from train_qlora.py runs (Phase 4).

    python scripts/plot_training.py runs/ru-guard-0.5b runs/ru-guard-0.5b-r8 --out docs/figures/training_0.5b.png

Each run folder needs train_log.csv and (optionally) val_metrics.csv. A resumed run can log a step twice;
the last row for a step wins.
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


def load_run(run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Train log (deduplicated by step) and val metrics (deduplicated by epoch)."""
    log = pd.read_csv(run_dir / "train_log.csv")
    log = log.drop_duplicates(subset=["step", "loss", "eval_loss"], keep="last").sort_values("step")
    val_path = run_dir / "val_metrics.csv"
    val = None
    if val_path.exists():
        val = pd.read_csv(val_path).drop_duplicates(subset=["epoch"], keep="last").sort_values("epoch")
    return log, val


def plot(runs: list[Path], out: Path) -> None:
    """Three panels: train/eval loss by step, val macro-F1 by epoch, val recall and FPR by epoch."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for run in runs:
        log, val = load_run(run)
        train = log[pd.to_numeric(log["loss"], errors="coerce").notna()]
        evals = log[pd.to_numeric(log["eval_loss"], errors="coerce").notna()]
        axes[0].plot(train["step"], train["loss"].astype(float), label=f"{run.name} train")
        if len(evals):
            axes[0].plot(evals["step"], evals["eval_loss"].astype(float), "o--", label=f"{run.name} val")
        if val is not None:
            axes[1].plot(val["epoch"], val["macro_f1"], "o-", label=run.name)
            axes[2].plot(val["epoch"], val["recall"], "o-", label=f"{run.name} recall")
            axes[2].plot(val["epoch"], val["fpr"], "x--", label=f"{run.name} FPR")
    axes[0].set(title="Loss", xlabel="optimizer step", ylabel="loss")
    axes[1].set(title="Val macro-F1 (generation)", xlabel="epoch", ylim=(0, 1.02))
    axes[2].set(title="Val recall and FPR (generation)", xlabel="epoch", ylim=(0, 1.02))
    for ax in axes:
        ax.legend(fontsize=7)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, default=Path("docs/figures/training.png"))
    args = ap.parse_args(argv)
    plot(args.runs, args.out)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
