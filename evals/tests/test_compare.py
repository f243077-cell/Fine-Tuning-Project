"""Tests for evals/compare.py: report and charts from tiny metrics files."""

import json
from pathlib import Path

from evals.compare import fmt, load_runs, main
from evals.metrics import evaluate


def write_run(runs: Path, name: str, preds: list[tuple[str, str | None]]) -> None:
    """One fake run directory with metrics.json."""
    rows = [{"label": lab, "attack_type": "override" if lab == "INJECTION" else None, "pred": p,
             "surface": "en", "source": "user_input", "hard_negative": False} for lab, p in preds]
    m = evaluate(rows, n_boot=20)
    m.update({"run": name, "split": "test", "rows": len(rows), "model": {}, "versions": {},
              "latency_seconds": {"p50": 0.1, "p95": 0.2}, "command": "x"})
    (runs / name).mkdir(parents=True)
    (runs / name / "metrics.json").write_text(json.dumps(m), encoding="utf-8")


def test_fmt() -> None:
    """Point with CI, plain point, and NaN."""
    assert fmt(0.5, [0.4, 0.6]) == "0.500 [0.40, 0.60]" and fmt(0.25) == "0.250" and fmt(float("nan")) == "n/a"


def test_report_written_with_notes(tmp_path: Path) -> None:
    """Runs are ordered, tables and charts are written, and notes are appended."""
    runs = tmp_path / "runs"
    write_run(runs, "qwen2.5-1.5b-zeroshot", [("INJECTION", "SAFE"), ("SAFE", "SAFE")])
    write_run(runs, "rules", [("INJECTION", "INJECTION|override"), ("SAFE", "SAFE")])
    assert [r["run"] for r in load_runs(runs)] == ["rules", "qwen2.5-1.5b-zeroshot"]
    notes = tmp_path / "notes.md"
    notes.write_text("## Findings\nhello\n", encoding="utf-8")
    out = tmp_path / "reports" / "baselines.md"
    out.parent.mkdir()
    assert main(["--runs", str(runs), "--out", str(out), "--notes", str(notes)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "| rules | 1.000" in text and text.rstrip().endswith("hello")
    assert (out.parent / "figures" / "baselines_recall_by_surface.png").exists()
