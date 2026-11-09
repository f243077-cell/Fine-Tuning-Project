"""Tests for the test-set lock scripts, plus the live check of data/eval/test.lock."""

from collections.abc import Callable
from pathlib import Path

import pytest

from scripts import lock_test, verify_test_lock
from scripts.locking import DEFAULT_TEST, content_sha256, lock_path_for, verify
from scripts.tests.helpers import full_test_rows


def test_hash_ignores_line_endings(tmp_path: Path) -> None:
    """CRLF and LF copies of the same content hash the same."""
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a.write_bytes(b'{"x": 1}\n{"y": 2}\n')
    b.write_bytes(b'{"x": 1}\r\n{"y": 2}\r\n')
    assert content_sha256(a) == content_sha256(b)


def test_lock_then_verify(write_jsonl: Callable) -> None:
    """Locking a valid set writes a lock that verifies."""
    test = write_jsonl(full_test_rows(), "test.jsonl")
    assert lock_test.main(["--test", str(test)]) == 0
    assert lock_path_for(test).read_text(encoding="utf-8").endswith("  test.jsonl\n")
    assert verify_test_lock.main(["--test", str(test)]) == 0


def test_verify_detects_change(write_jsonl: Callable) -> None:
    """Editing the locked file makes verification fail."""
    test = write_jsonl(full_test_rows(), "test.jsonl")
    assert lock_test.main(["--test", str(test)]) == 0
    test.write_text(test.read_text(encoding="utf-8").replace("intent 0", "intent X"), encoding="utf-8")
    ok, msg = verify(test)
    assert not ok and "HASH MISMATCH" in msg
    assert verify_test_lock.main(["--test", str(test)]) == 1


def test_lock_refuses_existing_lock(write_jsonl: Callable) -> None:
    """An existing lock is never overwritten."""
    test = write_jsonl(full_test_rows(), "test.jsonl")
    lock_path_for(test).write_text("old\n", encoding="utf-8")
    assert lock_test.main(["--test", str(test)]) == 2
    assert lock_path_for(test).read_text(encoding="utf-8") == "old\n"


def test_lock_refuses_invalid_set(write_jsonl: Callable) -> None:
    """A test set with validation errors is not locked."""
    rows = [r for r in full_test_rows() if r["surface"] != "ru_pure"]
    test = write_jsonl(rows, "test.jsonl")
    assert lock_test.main(["--test", str(test)]) == 1
    assert not lock_path_for(test).exists()


def test_verify_without_lock(tmp_path: Path) -> None:
    """No lock yet gives exit code 2."""
    assert verify_test_lock.main(["--test", str(tmp_path / "test.jsonl")]) == 2


def test_repo_test_set_matches_lock() -> None:
    """The real frozen test set matches its lock (skipped until the owner locks it)."""
    if not lock_path_for(DEFAULT_TEST).exists():
        pytest.skip("data/eval/test.lock not created yet")
    ok, msg = verify(DEFAULT_TEST)
    assert ok, msg
