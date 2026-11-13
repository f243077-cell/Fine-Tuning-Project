"""Build evals/reports/baselines.md (tables) and PNG charts from evals/reports/runs/*/metrics.json.

    python evals/compare.py
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RUNS = REPO / "evals" / "reports" / "runs"
ORDER = ["rules", "qwen2.5-1.5b-zeroshot", "qwen2.5-1.5b-fewshot", "llama-guard3-1b"]


def fmt(point: float, ci: list[float] | None = None) -> str:
    """0.812 [0.75, 0.86] style; n/a for NaN."""
    if point != point:  # NaN
        return "n/a"
    return f"{point:.3f}" if ci is None else f"{point:.3f} [{ci[0]:.2f}, {ci[1]:.2f}]"


def load_runs(runs_dir: Path, split: str = "test") -> list[dict]:
    """Metrics of every run on the split, in a stable order."""
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(runs_dir.glob("*/metrics.json"))]
    runs = [r for r in runs if r["split"] == split]
    return sorted(runs, key=lambda r: (ORDER.index(r["run"]) if r["run"] in ORDER else len(ORDER), r["run"]))


def overall_table(runs: list[dict]) -> list[str]:
    """Headline metrics with 95% CIs."""
    lines = ["| Model | Recall | FPR | Precision | F1 | Macro-F1 (attack type) | Invalid | p50 s | p95 s |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        p, c = r["overall"]["point"], r["overall"]["ci95"]
        lat = r["latency_seconds"]
        lines.append(f"| {r['run']} | {fmt(p['recall'], c['recall'])} | {fmt(p['fpr'], c['fpr'])} | "
                     f"{fmt(p['precision'], c['precision'])} | {fmt(p['f1'], c['f1'])} | "
                     f"{fmt(p['macro_f1_attack_type'], c['macro_f1_attack_type'])} | {fmt(p['invalid_rate'])} | "
                     f"{lat['p50']:.3f} | {lat['p95']:.3f} |")
    return lines


def cut_table(runs: list[dict], cut: str, metric: str) -> list[str]:
    """One metric per cut value (columns) per model (rows)."""
    values = sorted({v for r in runs for v in r["cuts"][cut]})
    lines = [f"| Model | {' | '.join(values)} |", "|---" * (len(values) + 1) + "|"]
    for r in runs:
        cells = []
        for v in values:
            m = r["cuts"][cut].get(v, {}).get(metric)
            cells.append(fmt(m["point"], m["ci95"]) if m else "")
        lines.append(f"| {r['run']} | {' | '.join(cells)} |")
    return lines


def chart(runs: list[dict], cut: str, metric: str, path: Path) -> None:
    """Grouped bar chart of one metric per cut value, with CI error bars."""
    values = sorted({v for r in runs for v in r["cuts"][cut]})
    fig, ax = plt.subplots(figsize=(8, 4))
    width = 0.8 / max(len(runs), 1)
    for i, r in enumerate(runs):
        pts, lo, hi = [], [], []
        for v in values:
            m = r["cuts"][cut].get(v, {}).get(metric, {"point": float("nan"), "ci95": [float("nan")] * 2})
            p = m["point"]
            pts.append(p)
            lo.append(p - m["ci95"][0] if p == p else 0)
            hi.append(m["ci95"][1] - p if p == p else 0)
        xs = [j + i * width for j in range(len(values))]
        ax.bar(xs, pts, width, yerr=[lo, hi], capsize=2, label=r["run"])
    ax.set_xticks([j + width * (len(runs) - 1) / 2 for j in range(len(values))], values)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel(metric)
    ax.set_title(f"{metric} by {cut} (95% CI)")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def build_report(runs: list[dict], out: Path) -> str:
    """Write charts and return the markdown body."""
    fig_dir = out.parent / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    chart(runs, "surface", "recall", fig_dir / "baselines_recall_by_surface.png")
    chart(runs, "attack_type", "recall", fig_dir / "baselines_recall_by_attack_type.png")
    chart(runs, "hard_negative", "fpr", fig_dir / "baselines_fpr_hard_negative.png")
    md = ["# Baselines on the frozen test set (Phase 3)", "",
          f"Test set: {runs[0]['rows'] if runs else 0} rows (150 INJECTION, 150 SAFE; 100 per surface). "
          "95% CIs from 1,000 bootstrap resamples (seed 1234). Invalid outputs count as flags (fail closed, D43).",
          "", "## Overall", "", *overall_table(runs), "",
          "## Recall by surface", "", *cut_table(runs, "surface", "recall"), "",
          "![recall by surface](figures/baselines_recall_by_surface.png)", "",
          "## FPR by surface", "", *cut_table(runs, "surface", "fpr"), "",
          "## Recall by attack type", "", *cut_table(runs, "attack_type", "recall"), "",
          "![recall by attack type](figures/baselines_recall_by_attack_type.png)", "",
          "## Recall and FPR by source", "", *cut_table(runs, "source", "recall"), "",
          *cut_table(runs, "source", "fpr"), "",
          "## FPR on hard negatives (True) vs plain SAFE (False)", "", *cut_table(runs, "hard_negative", "fpr"), "",
          "![FPR hard negatives](figures/baselines_fpr_hard_negative.png)", "",
          "## Runs", ""]
    for r in runs:
        md.append(f"- `{r['run']}`: `{r['command']}`; model {json.dumps(r['model'])}; versions {json.dumps(r['versions'])}")
    return "\n".join(md) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=Path, default=RUNS)
    ap.add_argument("--out", type=Path, default=REPO / "evals" / "reports" / "baselines.md")
    ap.add_argument("--notes", type=Path, default=REPO / "evals" / "reports" / "baselines_notes.md",
                    help="hand-written analysis appended to the report (kept across regenerations)")
    args = ap.parse_args(argv)
    runs = load_runs(args.runs)
    if not runs:
        print("no runs found", file=sys.stderr)
        return 1
    body = build_report(runs, args.out)
    if args.notes.exists():
        body += "\n" + args.notes.read_text(encoding="utf-8")
    args.out.write_text(body, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
