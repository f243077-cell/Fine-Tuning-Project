"""Apply a reviewed CSV (keep / fix / drop) to train/val JSONL and report the bad-row rate.

    python scripts/apply_review.py data/review/review_sample.csv --dry-run   # rate only
    python scripts/apply_review.py data/review/review_sample.csv             # apply
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.jsonl import content_sha256, dataset_sha256, format_validation_error, read_rows, write_rows  # noqa: E402
from training.schemas import DataRow  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DECISIONS = {"keep", "fix", "drop"}
TARGET_RATE = 0.10
REGENERATE_RATE = 0.15


def read_review(path: Path) -> list[dict]:
    """Rows of the review sheet with stripped values."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def _bool(value: str, default: bool) -> bool:
    """Parse true/false cells (blank keeps the default)."""
    if not value:
        return default
    if value.lower() in {"true", "1", "yes"}:
        return True
    if value.lower() in {"false", "0", "no"}:
        return False
    raise ValueError(f"not a boolean: {value!r}")


def fixed_row(original: DataRow, r: dict) -> DataRow:
    """The corrected row; raises ValueError if the fix is empty or invalid."""
    fields = ["fixed_text", "fixed_label", "fixed_attack_type", "fixed_surface", "fixed_hard_negative"]
    if not any(r.get(f) for f in fields):
        raise ValueError("decision is fix but no fixed_* column is filled")
    data = original.model_dump(mode="json")
    if r.get("fixed_text"):
        data["text"] = r["fixed_text"]
    if r.get("fixed_label"):
        data["label"] = r["fixed_label"].upper()
        if data["label"] == "SAFE":
            data["attack_type"] = None
        else:
            data["hard_negative"] = False
    if r.get("fixed_attack_type"):
        data["attack_type"] = r["fixed_attack_type"]
    if r.get("fixed_surface"):
        data["surface"] = r["fixed_surface"]
    data["hard_negative"] = _bool(r.get("fixed_hard_negative", ""), data["hard_negative"])
    try:
        return DataRow.model_validate(data)
    except ValidationError as e:
        raise ValueError(format_validation_error(e)) from e


def plan(review: list[dict], by_id: dict[str, DataRow]) -> tuple[dict[str, DataRow | None], list[str]]:
    """Map id to replacement (None = drop) for every fix/drop; collect errors with sheet row numbers."""
    changes: dict[str, DataRow | None] = {}
    errors: list[str] = []
    for n, r in enumerate(review, start=2):
        decision = r.get("decision", "").lower()
        rid = r.get("id", "")
        if decision not in DECISIONS:
            errors.append(f"row {n} ({rid}): decision must be keep, fix, or drop, got {decision!r}")
            continue
        original = by_id.get(rid)
        if original is None:
            errors.append(f"row {n} ({rid}): id not found in train/val (already applied or rebuilt?)")
            continue
        if original.text != r.get("text", ""):
            errors.append(f"row {n} ({rid}): text differs from the dataset; the sample is stale")
            continue
        if decision == "drop":
            changes[rid] = None
        elif decision == "fix":
            try:
                changes[rid] = fixed_row(original, r)
            except ValueError as e:
                errors.append(f"row {n} ({rid}): {e}")
    return changes, errors


def summary(review: list[dict]) -> dict:
    """Decision counts and the bad-row rate ((fix + drop) / reviewed)."""
    c = Counter(r["decision"].lower() for r in review)
    total = sum(c.values())
    rate = (c["fix"] + c["drop"]) / total if total else 0.0
    by_label = Counter((r["label"], r["decision"].lower()) for r in review)
    verdict = "go" if rate <= TARGET_RATE else ("review prompts" if rate <= REGENERATE_RATE else "regenerate")
    return {"reviewed": total, "keep": c["keep"], "fix": c["fix"], "drop": c["drop"],
            "bad_row_rate": round(rate, 4), "verdict": verdict,
            "by_label": {f"{k[0]}|{k[1]}": v for k, v in sorted(by_label.items())}}


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("review_csv", type=Path)
    ap.add_argument("--processed", type=Path, default=REPO / "data" / "processed")
    ap.add_argument("--dry-run", action="store_true", help="report the rate; change nothing")
    ap.add_argument("--force", action="store_true", help="apply even if a review report already exists")
    args = ap.parse_args(argv)
    report_path = args.processed / "review_report.json"
    if report_path.exists() and not args.dry_run and not args.force:
        print(f"{report_path} exists: this review was already applied (use --force to apply again)", file=sys.stderr)
        return 1
    splits: dict[str, list[DataRow]] = {}
    for split in ("train", "val"):
        rows, errors = read_rows(args.processed / f"{split}.jsonl")
        if errors:
            print(f"{split}.jsonl: {errors[:3]}", file=sys.stderr)
            return 1
        splits[split] = rows
    by_id = {r.id: r for rows in splits.values() for r in rows}
    review = read_review(args.review_csv)
    changes, errors = plan(review, by_id)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        print(f"{len(errors)} problem(s); nothing changed", file=sys.stderr)
        return 1
    result = summary(review)
    if not args.dry_run:
        for split, rows in splits.items():
            out = [changes[r.id] if r.id in changes else r for r in rows]
            write_rows(args.processed / f"{split}.jsonl", [r for r in out if r is not None])
        result["sha256"] = {s: content_sha256(args.processed / f"{s}.jsonl") for s in splits}
        result["sha256"]["dataset"] = dataset_sha256(result["sha256"]["train"], result["sha256"]["val"])
        result["review_csv_sha256"] = content_sha256(args.review_csv)
        report_path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
