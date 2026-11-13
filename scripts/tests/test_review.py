"""Tests for scripts/sample_for_review.py and scripts/apply_review.py."""

import csv
import json
from pathlib import Path

from scripts import apply_review, sample_for_review
from training.jsonl import read_rows, write_rows
from training.schemas import DataRow


def make_processed(tmp: Path) -> Path:
    """train.jsonl (8 rows) and val.jsonl (2 rows) in tmp/processed."""
    out = tmp / "processed"
    out.mkdir()
    rows = [DataRow(id=f"syn-{i:03d}", text=f"kuch text number {i}", source="user_input",
                    label="INJECTION" if i % 2 else "SAFE", attack_type="override" if i % 2 else None,
                    surface="ru_mix", origin="synthetic") for i in range(10)]
    write_rows(out / "train.jsonl", rows[:8])
    write_rows(out / "val.jsonl", rows[8:])
    return out


def fill(path: Path, decisions: dict[str, dict]) -> None:
    """Fill decision columns in the review sheet; unlisted rows are kept."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r.update(decisions.get(r["id"], {"decision": "keep"}))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sample_for_review.REVIEW_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def test_sample_is_deterministic_and_refuses_overwrite(tmp_path: Path) -> None:
    """Same seed gives the same sample; an existing sheet is not overwritten."""
    processed = make_processed(tmp_path)
    a = sample_for_review.sample(processed, 5, seed=3)
    b = sample_for_review.sample(processed, 5, seed=3)
    assert [r["id"] for r in a] == [r["id"] for r in b] and len(a) == 5
    out = tmp_path / "review.csv"
    assert sample_for_review.main(["--processed", str(processed), "--out", str(out), "--n", "4"]) == 0
    assert sample_for_review.main(["--processed", str(processed), "--out", str(out)]) == 1


def test_apply_review_fix_drop_and_rate(tmp_path: Path) -> None:
    """Fixes and drops are applied, the rate is reported, and a second apply is refused."""
    processed = make_processed(tmp_path)
    sheet = tmp_path / "review.csv"
    sample_for_review.main(["--processed", str(processed), "--out", str(sheet), "--n", "10"])
    fill(sheet, {"syn-001": {"decision": "fix", "fixed_label": "SAFE"},
                 "syn-002": {"decision": "drop"},
                 "syn-009": {"decision": "fix", "fixed_text": "naya text yahan"}})
    assert apply_review.main([str(sheet), "--processed", str(processed)]) == 0
    train, _ = read_rows(processed / "train.jsonl")
    val, _ = read_rows(processed / "val.jsonl")
    by_id = {r.id: r for r in train + val}
    assert "syn-002" not in by_id and len(train) == 7
    assert by_id["syn-001"].label == "SAFE" and by_id["syn-001"].attack_type is None
    assert by_id["syn-009"].text == "naya text yahan"
    report = json.loads((processed / "review_report.json").read_text(encoding="utf-8"))
    assert report["bad_row_rate"] == 0.3 and report["verdict"] == "regenerate"
    assert len(report["sha256"]["dataset"]) == 64
    assert apply_review.main([str(sheet), "--processed", str(processed)]) == 1


def test_apply_review_rejects_bad_sheet(tmp_path: Path) -> None:
    """Blank decisions or empty fixes change nothing."""
    processed = make_processed(tmp_path)
    before = (processed / "train.jsonl").read_bytes()
    sheet = tmp_path / "review.csv"
    sample_for_review.main(["--processed", str(processed), "--out", str(sheet), "--n", "10"])
    fill(sheet, {"syn-001": {"decision": ""}, "syn-003": {"decision": "fix"}})
    assert apply_review.main([str(sheet), "--processed", str(processed)]) == 1
    assert (processed / "train.jsonl").read_bytes() == before


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    """--dry-run reports without writing."""
    processed = make_processed(tmp_path)
    before = (processed / "train.jsonl").read_bytes()
    sheet = tmp_path / "review.csv"
    sample_for_review.main(["--processed", str(processed), "--out", str(sheet), "--n", "10"])
    fill(sheet, {"syn-002": {"decision": "drop"}})
    assert apply_review.main([str(sheet), "--processed", str(processed), "--dry-run"]) == 0
    assert (processed / "train.jsonl").read_bytes() == before
    assert not (processed / "review_report.json").exists()
