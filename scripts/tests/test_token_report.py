"""Tests for scripts/token_report.py with a fake character-level tokenizer (no download)."""

from collections.abc import Callable
from pathlib import Path

from scripts.tests.helpers import make_row
from scripts.token_report import report, worst_case_windows


class FakeTokenizer:
    """One token per 4 characters of the rendered chat."""

    def apply_chat_template(self, messages: list[dict], tokenize: bool = False) -> str:
        """Join role and content like a chat template."""
        return "".join(f"<{m['role']}>{m['content']}" for m in messages)

    def __call__(self, text: str, add_special_tokens: bool = False) -> dict:
        """Return fake input ids."""
        return {"input_ids": list(range(len(text) // 4))}


def test_worst_case_windows_are_full_size() -> None:
    """Windows are exactly window_chars long, even from short texts."""
    wins = worst_case_windows(["abc", "defg"], 50)
    assert len(wins) == 3 and all(len(w) == 50 for w in wins)
    assert worst_case_windows([], 50) == []


def test_report_fits_and_fails(write_jsonl: Callable[[list[dict], str], Path]) -> None:
    """The fits flag follows max_seq_len."""
    path = write_jsonl([make_row(1, text="abcdefghij " * 20), make_row(2, text="short text")], "rows.jsonl")
    ok = report(FakeTokenizer(), [path], window_chars=400, max_seq_len=512)
    assert ok["fits"] and ok["files"]["rows.jsonl"]["n"] == 2
    bad = report(FakeTokenizer(), [path], window_chars=4000, max_seq_len=512)
    assert not bad["fits"] and bad["largest"] > 512
