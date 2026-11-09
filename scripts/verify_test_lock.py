"""Check that the frozen test set still matches data/eval/test.lock. Exit 0 ok, 1 mismatch, 2 no lock yet."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.locking import DEFAULT_TEST, lock_path_for, verify  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--test", type=Path, default=DEFAULT_TEST)
    args = p.parse_args(argv)

    if not lock_path_for(args.test).exists():
        print(f"no lock yet: {lock_path_for(args.test)} (run scripts/lock_test.py after Phase 1 authoring)")
        return 2
    ok, msg = verify(args.test)
    print(msg, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
