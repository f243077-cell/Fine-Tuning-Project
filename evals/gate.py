"""Regression gate (Phase 5): exit non-zero if any release metric falls past its threshold.

    python evals/gate.py                                         # thresholds' own release run
    python evals/gate.py --metrics evals/reports/runs/<run>/metrics.json
    python evals/gate.py --make evals/reports/runs/<run>         # write evals/thresholds.json from a release run

Thresholds = release metrics minus a 2-point tolerance for "higher is better" metrics, plus 2 points for
"lower is better" metrics (FPR, invalid rate), clamped to [0, 1].
"""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
THRESHOLDS = REPO / "evals" / "thresholds.json"
TOLERANCE = 0.02
# name -> (path into metrics.json, direction)
METRICS = {
    "recall": (("overall", "point", "recall"), "min"),
    "f1": (("overall", "point", "f1"), "min"),
    "macro_f1_attack_type": (("overall", "point", "macro_f1_attack_type"), "min"),
    "recall_roman_urdu": (("cuts", "language", "roman_urdu", "recall", "point"), "min"),
    "fpr": (("overall", "point", "fpr"), "max"),
    "fpr_roman_urdu": (("cuts", "language", "roman_urdu", "fpr", "point"), "max"),
    "invalid_rate": (("overall", "point", "invalid_rate"), "max"),
}


def read_value(metrics: dict, path: tuple[str, ...]) -> float:
    """Nested lookup; fails loudly if a metric is missing."""
    node = metrics
    for key in path:
        if key not in node:
            raise KeyError(f"metric path {'.'.join(path)} missing (rescore the run: python evals/rescore.py)")
        node = node[key]
    return float(node)


def make_thresholds(run_dir: Path, tolerance: float = TOLERANCE) -> dict:
    """Thresholds from a release run's metrics.json."""
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    out = {"release_run": metrics["run"], "release_metrics": str(Path(run_dir, "metrics.json").as_posix()),
           "tolerance": tolerance, "min": {}, "max": {}}
    for name, (path, direction) in METRICS.items():
        v = read_value(metrics, path)
        if direction == "min":
            out["min"][name] = round(max(0.0, v - tolerance), 4)
        else:
            out["max"][name] = round(min(1.0, v + tolerance), 4)
    return out


def check(metrics: dict, thresholds: dict) -> list[str]:
    """Human-readable failures (empty when the gate passes)."""
    failures = []
    for name, floor in thresholds["min"].items():
        v = read_value(metrics, METRICS[name][0])
        if v < floor:
            failures.append(f"{name} {v:.4f} < {floor:.4f}")
    for name, ceiling in thresholds["max"].items():
        v = read_value(metrics, METRICS[name][0])
        if v > ceiling:
            failures.append(f"{name} {v:.4f} > {ceiling:.4f}")
    return failures


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--thresholds", type=Path, default=THRESHOLDS)
    ap.add_argument("--metrics", type=Path, help="metrics.json to check (default: the release run)")
    ap.add_argument("--make", type=Path, metavar="RUN_DIR", help="write thresholds from this release run")
    args = ap.parse_args(argv)
    if args.make:
        data = make_thresholds(args.make)
        args.thresholds.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {args.thresholds}")
        return 0
    thresholds = json.loads(args.thresholds.read_text(encoding="utf-8"))
    metrics_path = args.metrics or REPO / thresholds["release_metrics"]
    failures = check(json.loads(Path(metrics_path).read_text(encoding="utf-8")), thresholds)
    for f in failures:
        print(f"FAIL {f}")
    print("gate: FAIL" if failures else "gate: PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
