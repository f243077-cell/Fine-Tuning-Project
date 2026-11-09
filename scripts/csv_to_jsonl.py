"""Convert an authoring CSV (seeds or test) to JSONL through the Pydantic schema."""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError  # noqa: E402

from scripts.locking import lock_path_for  # noqa: E402
from training.jsonl import format_validation_error, write_rows  # noqa: E402
from training.schemas import DataRow  # noqa: E402

COLUMNS = ["intent_id", "surface", "source", "label", "attack_type", "hard_negative", "text", "notes"]
_TRUE = {"yes", "y", "true", "1"}
_FALSE = {"", "no", "n", "false", "0"}


def _parse_bool(value: str) -> bool:
    """Parse a yes/empty spreadsheet cell."""
    v = value.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ValueError(f"hard_negative must be 'yes' or empty, got {value!r}")


def _row_to_dict(cells: dict[str, str], origin: str, index: int) -> dict:
    """Map one CSV row to DataRow fields."""
    get = lambda k: (cells.get(k) or "").strip()  # noqa: E731
    intent_id = get("intent_id") or None
    surface = get("surface")
    row_id = f"{origin}-{intent_id}-{surface}" if intent_id else f"{origin}-{index:05d}"
    return {
        "id": row_id,
        "text": (cells.get("text") or "").strip(),
        "source": get("source"),
        "label": get("label").upper(),
        "attack_type": get("attack_type") or None,
        "surface": surface,
        "origin": origin,
        "intent_id": intent_id,
        "hard_negative": _parse_bool(get("hard_negative")),
    }


def convert(csv_path: Path, origin: str) -> tuple[list[DataRow], list[str]]:
    """Parse a CSV; return valid rows and 'row N: problem' errors (N = spreadsheet row)."""
    rows: list[DataRow] = []
    errors: list[str] = []
    seen: dict[str, int] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            return [], [f"header: missing columns {', '.join(missing)}"]
        for index, cells in enumerate(reader, start=1):
            line = index + 1
            if not any((v or "").strip() for v in cells.values() if isinstance(v, str)):
                continue
            try:
                row = DataRow.model_validate(_row_to_dict(cells, origin, index))
            except ValidationError as e:
                errors.append(f"row {line}: {format_validation_error(e)}")
                continue
            except ValueError as e:
                errors.append(f"row {line}: {e}")
                continue
            if row.id in seen:
                errors.append(f"row {line}: duplicate id {row.id} (also row {seen[row.id]})")
                continue
            seen[row.id] = line
            rows.append(row)
    return rows, errors


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--origin", choices=["seed", "test"], required=True)
    p.add_argument("--force", action="store_true", help="overwrite an existing, unlocked output file")
    args = p.parse_args(argv)

    if lock_path_for(args.out).exists():
        print(f"refused: {args.out} is frozen by {lock_path_for(args.out)}; write a new version file instead", file=sys.stderr)
        return 2
    if args.out.exists() and not args.force:
        print(f"refused: {args.out} exists; pass --force to overwrite", file=sys.stderr)
        return 2

    rows, errors = convert(args.csv, args.origin)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(f"{len(errors)} error(s); nothing written", file=sys.stderr)
        return 1
    n = write_rows(args.out, rows)
    print(f"wrote {n} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
