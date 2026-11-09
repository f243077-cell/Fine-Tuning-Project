"""Tests for scripts/validate_data.py."""

from collections.abc import Callable

import pytest

from scripts.tests.helpers import ATTACKS, full_test_rows, make_row
from scripts.validate_data import main, validate
from training.schemas import DataRow


def _rows(dicts: list[dict]) -> list[DataRow]:
    """Parse dicts into DataRow objects."""
    return [DataRow.model_validate(d) for d in dicts]


def _seed_rows() -> list[dict]:
    """Seeds that fill every required seed cell."""
    rows, n = [], 0
    for c in ATTACKS + [None]:
        for s in ("ru_mix", "ru_pure"):
            n += 1
            label = "INJECTION" if c else "SAFE"
            rows.append(make_row(n, label=label, attack_type=c, surface=s))
    return rows


def test_full_test_set_has_no_errors() -> None:
    """A complete triplet fixture passes (target-count warnings are allowed)."""
    rep = validate(_rows(full_test_rows()))
    assert rep.kind == "test"
    assert rep.errors == []
    assert any("coverage" in i for i in rep.info)


def test_seed_set_has_no_errors() -> None:
    """Seeds covering every class in ru_mix and ru_pure pass."""
    rep = validate(_rows(_seed_rows()))
    assert rep.kind == "seed" and rep.errors == []
    assert any("persona has 2 rows" in w for w in rep.warnings)


def test_empty_required_cell_is_flagged() -> None:
    """Removing every persona row leaves empty required cells."""
    rows = [r for r in _seed_rows() if r["attack_type"] != "persona"]
    errors = validate(_rows(rows)).errors
    assert "empty coverage cell: class=persona surface=ru_mix source=any" in errors


def test_intent_missing_surface_is_flagged() -> None:
    """A test intent without its ru_pure row is reported."""
    rows = [r for r in full_test_rows() if not (r["intent_id"] == "t-000" and r["surface"] == "ru_pure")]
    assert "intent t-000: missing surface(s) ru_pure" in validate(_rows(rows)).errors


def test_inconsistent_intent_is_flagged() -> None:
    """Rows of one intent must share label, attack_type, source, and hard_negative."""
    rows = full_test_rows()
    rows[0] = {**rows[0], "source": "tool_output"}
    errors = validate(_rows(rows)).errors
    assert any(e.startswith("intent t-000: label/attack_type/source") for e in errors)


def test_duplicates_are_flagged() -> None:
    """Duplicate ids and duplicate normalized text per source are errors."""
    rows = _seed_rows()
    rows.append({**rows[0]})
    rows.append({**rows[1], "id": "other", "text": "  " + rows[1]["text"].upper()})
    errors = validate(_rows(rows)).errors
    assert any(e.startswith("duplicate id r-0001") for e in errors)
    assert any(e.startswith("duplicate text") and "other" in e for e in errors)


def test_main_reports_schema_errors(write_jsonl: Callable, capsys: pytest.CaptureFixture[str]) -> None:
    """Schema errors carry line numbers and give exit code 1."""
    rows = _seed_rows() + [make_row(99, label="INJECTION", attack_type=None)]
    assert main([str(write_jsonl(rows))]) == 1
    assert "ERROR: line 13: row: attack_type is required" in capsys.readouterr().out


def test_main_ok(write_jsonl: Callable, capsys: pytest.CaptureFixture[str]) -> None:
    """A clean file exits 0 and prints the coverage matrix."""
    assert main([str(write_jsonl(full_test_rows()))]) == 0
    out = capsys.readouterr().out
    assert "0 error(s)" in out and "class" in out
