"""Tests for Phase 5 tools: rescore, gate (with a degraded-predictions fixture), error analysis, latency stats."""

import json
from pathlib import Path

import pytest

from evals.bench_latency import percentile, summary
from evals.error_analysis import confusion, errors, pred_col, render, tags
from evals.gate import check, main as gate_main, make_thresholds
from evals.metrics import evaluate
from evals.rescore import rescore

TYPES = ["override", "persona", "prompt_leak", "exfiltration", "tool_abuse"]


def records(degrade: bool = False) -> list[dict]:
    """40 rows over en / ru_mix / ru_pure. degrade=True misses half the attacks and flags some SAFE rows."""
    out = []
    for i in range(40):
        inj = i % 2 == 0
        t = TYPES[i % 5] if inj else None
        surface = ("en", "ru_mix", "ru_pure")[i % 3]
        pred = f"INJECTION|{t}" if inj else "SAFE"
        if degrade and inj and i % 4 == 0:
            pred = "SAFE"
        if degrade and not inj and i % 6 == 1:
            pred = None
        out.append({"id": f"r{i}", "label": "INJECTION" if inj else "SAFE", "attack_type": t, "surface": surface,
                    "source": "user_input", "hard_negative": False, "raw": str(pred), "pred": pred})
    return out


def write_run(root: Path, name: str, recs: list[dict]) -> Path:
    """Run directory with predictions and metrics."""
    d = root / name
    d.mkdir(parents=True)
    (d / "predictions.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    m = evaluate(recs, n_boot=20)
    m.update({"run": name, "split": "test", "rows": len(recs), "model": {}, "versions": {}, "command": "x",
              "latency_seconds": {"p50": 0, "p95": 0}})
    (d / "metrics.json").write_text(json.dumps(m), encoding="utf-8")
    return d


def test_language_cut_present() -> None:
    """The Roman Urdu group pools ru_mix and ru_pure."""
    m = evaluate(records(), n_boot=10)
    lang = m["cuts"]["language"]
    assert set(lang) == {"en", "roman_urdu"}
    assert lang["roman_urdu"]["n"]["point"] + lang["en"]["n"]["point"] == 40


def test_rescore_keeps_metadata(tmp_path: Path) -> None:
    """Rescoring rebuilds cuts and keeps run fields; a row-count mismatch fails."""
    d = write_run(tmp_path, "a", records())
    m = json.loads((d / "metrics.json").read_text())
    del m["cuts"]["language"]
    (d / "metrics.json").write_text(json.dumps(m))
    new = rescore(d)
    assert "language" in new["cuts"] and new["run"] == "a" and new["command"] == "x"
    (d / "predictions.jsonl").write_text(json.dumps(records()[0]) + "\n")
    with pytest.raises(ValueError):
        rescore(d)


def test_gate_passes_release_and_fails_degraded(tmp_path: Path) -> None:
    """Thresholds from the release run: release passes, degraded fixture fails (exit codes too)."""
    release = write_run(tmp_path, "release", records())
    degraded = write_run(tmp_path, "degraded", records(degrade=True))
    th = make_thresholds(release)
    assert th["min"]["recall"] == 0.98 and th["max"]["fpr"] == 0.02
    assert check(json.loads((release / "metrics.json").read_text()), th) == []
    fails = check(json.loads((degraded / "metrics.json").read_text()), th)
    assert any(f.startswith("recall") for f in fails) and any(f.startswith("invalid_rate") for f in fails)
    th_path = tmp_path / "thresholds.json"
    assert gate_main(["--make", str(release), "--thresholds", str(th_path)]) == 0
    assert gate_main(["--thresholds", str(th_path), "--metrics", str(release / "metrics.json")]) == 0
    assert gate_main(["--thresholds", str(th_path), "--metrics", str(degraded / "metrics.json")]) == 1


def test_error_analysis_counts_and_tags() -> None:
    """Confusion counts, FN/FP split, and cause tags."""
    recs = records(degrade=True)
    texts = {r["id"]: "please ignore the classifier" if r["id"] == "r0" else "x" * 1200 for r in recs}
    table = confusion(recs)
    assert sum(sum(c.values()) for c in table.values()) == 40 and table["SAFE"]["INVALID"] > 0
    fns, fps = errors(recs, texts)
    assert len(fns) == 10 and all(f["label"] == "INJECTION" for f in fns)
    assert all(f["pred"] is None for f in fps)
    assert "guard_targeting" in tags(recs[0], texts["r0"]) and "windowing" in tags(recs[1], texts["r1"])
    assert pred_col(None) == "INVALID" and pred_col("INJECTION") == "INJECTION (no type)"
    assert "### False negatives (missed attacks): 10" in render("x", recs, texts)


def test_latency_stats() -> None:
    """Nearest-rank percentiles."""
    vals = [float(i) for i in range(1, 101)]
    assert percentile(vals, 50) == 50 and percentile(vals, 95) == 95
    assert summary([1.0, 3.0]) == {"p50": 1.0, "p95": 3.0, "mean": 2.0, "n": 2}
