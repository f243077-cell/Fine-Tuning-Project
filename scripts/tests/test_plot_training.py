"""Tests for scripts/plot_training.py with tiny fake run logs."""

from pathlib import Path

from scripts.plot_training import load_run, main


def fake_run(root: Path, name: str) -> Path:
    """A run folder with a resumed (duplicated) step and two val epochs."""
    run = root / name
    run.mkdir()
    (run / "train_log.csv").write_text(
        "step,epoch,loss,eval_loss,learning_rate,grad_norm\n"
        "10,0.1,2.0,,0.0002,1.0\n20,0.2,1.0,,0.0002,1.0\n20,0.2,1.0,,0.0002,1.0\n"
        "137,1.0,,0.5,,\n", encoding="utf-8")
    (run / "val_metrics.csv").write_text(
        "epoch,step,n,recall,fpr,invalid_rate,macro_f1,exact_match\n"
        "1.0,137,200,0.8,0.1,0.0,0.6,0.7\n2.0,274,200,0.9,0.05,0.0,0.7,0.8\n", encoding="utf-8")
    return run


def test_load_run_dedups(tmp_path: Path) -> None:
    """The duplicated step 20 appears once."""
    log, val = load_run(fake_run(tmp_path, "a"))
    assert list(log["step"]) == [10, 20, 137] and len(val) == 2


def test_plot_writes_png(tmp_path: Path) -> None:
    """Two runs on one figure."""
    out = tmp_path / "fig" / "t.png"
    assert main([str(fake_run(tmp_path, "a")), str(fake_run(tmp_path, "b")), "--out", str(out)]) == 0
    assert out.exists() and out.stat().st_size > 0
