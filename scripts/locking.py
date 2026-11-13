"""Hashing helpers for the frozen test-set lock (data/eval/test.lock)."""

from pathlib import Path

from training.jsonl import content_sha256

__all__ = ["DEFAULT_TEST", "content_sha256", "format_lock", "lock_path_for", "read_lock", "verify"]

DEFAULT_TEST = Path(__file__).resolve().parents[1] / "data" / "eval" / "test.jsonl"


def lock_path_for(jsonl: Path) -> Path:
    """Lock file that freezes a JSONL file (test.jsonl -> test.lock)."""
    return jsonl.with_suffix(".lock")


def format_lock(digest: str, jsonl: Path) -> str:
    """Lock file body in sha256sum style."""
    return f"{digest}  {jsonl.name}\n"


def read_lock(lock: Path) -> tuple[str, str]:
    """Return (digest, file name) from a lock file; raise ValueError if malformed."""
    parts = lock.read_text(encoding="utf-8").split()
    if len(parts) != 2 or len(parts[0]) != 64:
        raise ValueError(f"malformed lock file {lock}")
    return parts[0], parts[1]


def verify(jsonl: Path) -> tuple[bool, str]:
    """Check jsonl against its lock; return (ok, message)."""
    lock = lock_path_for(jsonl)
    if not lock.exists():
        return False, f"no lock file at {lock}"
    if not jsonl.exists():
        return False, f"{jsonl} is missing but {lock} exists"
    try:
        expected, name = read_lock(lock)
    except ValueError as e:
        return False, str(e)
    if name != jsonl.name:
        return False, f"{lock} names {name}, not {jsonl.name}"
    actual = content_sha256(jsonl)
    if actual != expected:
        return False, f"HASH MISMATCH for {jsonl}: lock {expected}, file {actual}. The frozen test set changed; tell the owner."
    return True, f"ok: {jsonl.name} matches {lock.name} ({actual[:12]})"
