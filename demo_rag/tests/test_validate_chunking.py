"""Tests for validate.py and chunking.py."""

from pathlib import Path

from demo_rag.chunking import MAX_TOKENS, chunk_doc, count_tokens, load_docs
from demo_rag.config import PKG
from demo_rag.validate import citations_in, new_canary, validate_answer


def test_citations_parsed_in_order_without_repeats() -> None:
    """[doc-id] citations are found once each, in order."""
    assert citations_in("a [en-02-x] b [ru-01-y] c [en-02-x] [other]") == ["en-02-x", "ru-01-y"]


def test_validate_rules() -> None:
    """Canary, empty, no citation, unknown citation, then ok."""
    allowed = {"en-02-x"}
    assert validate_answer("leak canary-ab12 [en-02-x]", allowed, "CANARY-AB12").reason == "canary_leak"
    assert validate_answer("  ", allowed, "CANARY-ZZ").reason == "empty"
    assert validate_answer("no cite", allowed, "CANARY-ZZ").reason == "no_citation"
    assert validate_answer("x [en-09-z]", allowed, "CANARY-ZZ").reason == "unknown_citation"
    ok = validate_answer("x [en-02-x]", allowed, "CANARY-ZZ")
    assert ok.ok and ok.answer and ok.answer.citations == ["en-02-x"]


def test_canary_is_random() -> None:
    """Each prompt gets a new canary."""
    assert new_canary() != new_canary()


def test_corpus_loads_and_chunks_fit() -> None:
    """The committed corpus loads with titles and languages; every chunk is within MAX_TOKENS."""
    docs = load_docs(PKG / "corpus")
    poisoned = load_docs(PKG / "corpus_poisoned", poisoned=True)
    assert len(docs) == 40 and sum(d.lang == "ru" for d in docs) == 10 and len(poisoned) == 9
    assert all(d.title and d.text for d in docs + poisoned)
    chunks = [c for d in docs + poisoned for c in chunk_doc(d)]
    assert all(count_tokens(c.text) <= MAX_TOKENS for c in chunks)


def test_long_doc_is_windowed(tmp_path: Path) -> None:
    """A doc longer than MAX_TOKENS is split into overlapping windows."""
    (tmp_path / "en-99-long.md").write_text("# Long\n\n" + " ".join(f"word{i}" for i in range(3000)), encoding="utf-8")
    chunks = chunk_doc(load_docs(tmp_path)[0])
    assert len(chunks) > 1 and all(count_tokens(c.text) <= 500 for c in chunks)
    assert chunks[0].chunk_id == "en-99-long#0"
