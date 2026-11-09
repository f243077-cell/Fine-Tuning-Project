"""Tests for scripts/csv_to_jsonl.py."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.csv_to_jsonl import main

GOOD = [
    {"intent_id": "t-001", "surface": "en", "source": "user_input", "label": "injection",
     "attack_type": "override", "text": "placeholder injection"},
    {"intent_id": "t-002", "surface": "ru_mix", "source": "retrieved_chunk", "label": "SAFE",
     "hard_negative": "yes", "text": "placeholder hard negative"},
]


def test_converts_valid_csv(tmp_path: Path, write_csv: Callable) -> None:
    """Valid rows become JSONL with stable ids and parsed booleans."""
    out = tmp_path / "out.jsonl"
    assert main([str(write_csv(GOOD)), str(out), "--origin", "test"]) == 0
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in rows] == ["test-t-001-en", "test-t-002-ru_mix"]
    assert rows[0]["label"] == "INJECTION"
    assert rows[1]["hard_negative"] is True
    assert b"\r\n" not in out.read_bytes()


def test_seed_ids_use_row_index(tmp_path: Path, write_csv: Callable) -> None:
    """Seeds without intent_id get index-based ids."""
    rows = [{**r, "intent_id": ""} for r in GOOD]
    out = tmp_path / "s.jsonl"
    assert main([str(write_csv(rows)), str(out), "--origin", "seed"]) == 0
    ids = [json.loads(line)["id"] for line in out.read_text(encoding="utf-8").splitlines()]
    assert ids == ["seed-00001", "seed-00002"]


def test_reports_row_errors_and_writes_nothing(
    tmp_path: Path, write_csv: Callable, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bad rows are reported with spreadsheet row numbers; no output is written."""
    bad = GOOD + [
        {"intent_id": "t-003", "surface": "urdu", "source": "user_input", "label": "SAFE", "text": "x"},
        {"intent_id": "t-004", "surface": "en", "source": "user_input", "label": "INJECTION", "text": "y"},
        {"intent_id": "t-005", "surface": "en", "source": "user_input", "label": "SAFE",
         "hard_negative": "maybe", "text": "z"},
        {"intent_id": "t-001", "surface": "en", "source": "user_input", "label": "SAFE", "text": "dup"},
    ]
    out = tmp_path / "out.jsonl"
    assert main([str(write_csv(bad)), str(out), "--origin", "test"]) == 1
    err = capsys.readouterr().err
    assert "row 4: surface" in err
    assert "row 5:" in err and "attack_type is required" in err
    assert "row 6: hard_negative must be" in err
    assert "row 7: duplicate id test-t-001-en (also row 2)" in err
    assert not out.exists()


def test_missing_column(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A CSV without the required header is rejected."""
    p = tmp_path / "bad.csv"
    p.write_text("surface,text\nen,hello\n", encoding="utf-8")
    assert main([str(p), str(tmp_path / "o.jsonl"), "--origin", "seed"]) == 1
    assert "missing columns" in capsys.readouterr().err


def test_refuses_locked_output(tmp_path: Path, write_csv: Callable) -> None:
    """A JSONL frozen by a .lock file is never overwritten, even with --force."""
    out = tmp_path / "test.jsonl"
    out.write_text("original\n", encoding="utf-8")
    (tmp_path / "test.lock").write_text("abc  test.jsonl\n", encoding="utf-8")
    assert main([str(write_csv(GOOD)), str(out), "--origin", "test", "--force"]) == 2
    assert out.read_text(encoding="utf-8") == "original\n"


def test_existing_output_needs_force(tmp_path: Path, write_csv: Callable) -> None:
    """An existing unlocked output is only replaced with --force."""
    out = tmp_path / "seeds.jsonl"
    out.write_text("old\n", encoding="utf-8")
    src = str(write_csv(GOOD))
    assert main([src, str(out), "--origin", "seed"]) == 2
    assert main([src, str(out), "--origin", "seed", "--force"]) == 0
