"""Freeze the hand-written test set: validate it, then write data/eval/test.lock (owner runs this once)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.locking import DEFAULT_TEST, content_sha256, format_lock, lock_path_for  # noqa: E402
from scripts.validate_data import validate  # noqa: E402
from training.jsonl import read_rows  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--test", type=Path, default=DEFAULT_TEST)
    args = p.parse_args(argv)

    lock = lock_path_for(args.test)
    if lock.exists():
        print(f"refused: {lock} already exists. A changed test set needs owner approval and a new version file.",
              file=sys.stderr)
        return 2
    if not args.test.exists():
        print(f"refused: {args.test} not found", file=sys.stderr)
        return 1
    rows, parse_errors = read_rows(args.test)
    rep = validate(rows, "test")
    errors = parse_errors + rep.errors
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print("refused: fix validation errors before locking", file=sys.stderr)
        return 1
    for w in rep.warnings:
        print(f"WARNING: {w}")
    digest = content_sha256(args.test)
    with lock.open("w", encoding="utf-8", newline="\n") as f:
        f.write(format_lock(digest, args.test))
    print(f"locked {args.test.name}: {len(rows)} rows, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
