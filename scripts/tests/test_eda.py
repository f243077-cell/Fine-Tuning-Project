"""Tests for scripts/eda.py."""

from collections.abc import Callable
from pathlib import Path

from scripts.eda import main
from scripts.tests.helpers import full_test_rows, make_row


def test_writes_both_figures(tmp_path: Path, write_jsonl: Callable) -> None:
    """Both PNG files are created and non-empty."""
    out = tmp_path / "figs"
    assert main([str(write_jsonl(full_test_rows())), "--name", "fx", "--out", str(out)]) == 0
    for f in ("fx_lengths.png", "fx_coverage.png"):
        assert (out / f).stat().st_size > 1000


def test_refuses_invalid_file(tmp_path: Path, write_jsonl: Callable) -> None:
    """A file with schema errors produces no figures."""
    bad = write_jsonl([make_row(1, label="INJECTION")])
    out = tmp_path / "figs"
    assert main([str(bad), "--out", str(out)]) == 1
    assert not out.exists()
