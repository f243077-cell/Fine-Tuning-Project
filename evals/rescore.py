"""Recompute metrics.json from saved predictions.jsonl (no model calls), e.g. after a new cut is added.

    python evals/rescore.py                       # every run under evals/reports/runs
    python evals/rescore.py evals/reports/runs/rules

Only the "overall" and "cuts" blocks change; run name, model, versions, latency and command are kept.
"""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from evals.metrics import evaluate  # noqa: E402

RUNS = REPO / "evals" / "reports" / "runs"


def rescore(run_dir: Path) -> dict:
    """Re-evaluate one run directory in place and return the new metrics."""
    rows = [json.loads(line) for line in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    path = run_dir / "metrics.json"
    metrics = json.loads(path.read_text(encoding="utf-8"))
    if metrics.get("rows") != len(rows):
        raise ValueError(f"{run_dir}: metrics.json has {metrics.get('rows')} rows, predictions have {len(rows)}")
    metrics.update(evaluate(rows))
    path.write_text(json.dumps(metrics, indent=1), encoding="utf-8")
    return metrics


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", type=Path, nargs="*")
    args = ap.parse_args(argv)
    dirs = args.runs or sorted(p.parent for p in RUNS.glob("*/metrics.json"))
    for d in dirs:
        rescore(d)
        print(f"rescored {d.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
