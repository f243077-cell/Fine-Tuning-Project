"""Sample random processed rows into a CSV for human review (keep / fix / drop).

    python scripts/sample_for_review.py --n 200 --out data/review/review_sample.csv
"""

import argparse
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.jsonl import read_rows  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
REVIEW_COLUMNS = [
    "id", "split", "label", "attack_type", "surface", "source", "hard_negative", "text",
    "decision", "fixed_text", "fixed_label", "fixed_attack_type", "fixed_surface", "fixed_hard_negative", "notes",
]


def sample(processed: Path, n: int, seed: int) -> list[dict]:
    """n random rows from train.jsonl and val.jsonl, as review dicts sorted by id."""
    pool: list[dict] = []
    for split in ("train", "val"):
        rows, errors = read_rows(processed / f"{split}.jsonl")
        if errors:
            raise SystemExit(f"{split}.jsonl: {errors[:3]}")
        pool += [{**r.model_dump(mode="json"), "split": split} for r in rows]
    pool.sort(key=lambda r: r["id"])
    picked = random.Random(seed).sample(pool, min(n, len(pool)))
    return sorted(picked, key=lambda r: r["id"])


def write_csv(path: Path, rows: list[dict]) -> None:
    """Write the review sheet (UTF-8 with BOM so spreadsheets show Roman Urdu and symbols)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c, "")) for c in REVIEW_COLUMNS})


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--processed", type=Path, default=REPO / "data" / "processed")
    ap.add_argument("--out", type=Path, default=REPO / "data" / "review" / "review_sample.csv")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--force", action="store_true", help="overwrite an existing review sheet")
    args = ap.parse_args(argv)
    if args.out.exists() and not args.force:
        print(f"refusing to overwrite {args.out} (it may hold review work); use --force", file=sys.stderr)
        return 1
    rows = sample(args.processed, args.n, args.seed)
    write_csv(args.out, rows)
    print(f"wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
