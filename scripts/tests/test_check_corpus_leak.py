"""Tests for scripts/check_corpus_leak.py."""

from pathlib import Path

from scripts.check_corpus_leak import DEFAULT_PATHS, check, texts_of


def test_texts_of_md_and_yaml(tmp_path: Path) -> None:
    """Markdown splits into paragraphs; YAML yields long string fields."""
    md = tmp_path / "a.md"
    md.write_text("# t\n\nfirst paragraph is long enough\n\nsecond paragraph is long enough too\n", encoding="utf-8")
    y = tmp_path / "b.yaml"
    y.write_text("items:\n  - q: a short\n    text: this string is long enough to count\n", encoding="utf-8")
    assert [t for _, t in texts_of(md)] == ["first paragraph is long enough", "second paragraph is long enough too"]
    assert [t for _, t in texts_of(y)] == ["this string is long enough to count"]


def test_repo_demo_texts_do_not_leak() -> None:
    """The committed corpus, poisoned docs, notes, attack suite, and golden set are far from every test row."""
    assert check(DEFAULT_PATHS) == []
