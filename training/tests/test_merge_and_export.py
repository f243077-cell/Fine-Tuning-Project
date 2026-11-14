"""Tests for the GPU-free helpers in training/merge_and_export.py."""

from pathlib import Path

import pytest

from training.merge_and_export import SANITY, find_gguf, sha256_file


def test_find_gguf_in_build_or_sibling(tmp_path: Path) -> None:
    """Unsloth may write into the build folder or into '<build>_gguf'; quant matching ignores case."""
    build = tmp_path / "_gguf_build"
    (tmp_path / "_gguf_build_gguf").mkdir()
    (tmp_path / "_gguf_build_gguf" / "model.Q8_0.gguf").write_bytes(b"x")
    build.mkdir()
    (build / "model.Q4_K_M.gguf").write_bytes(b"y")
    assert find_gguf(build, "q4_k_m").name == "model.Q4_K_M.gguf"
    assert find_gguf(build, "q8_0").name == "model.Q8_0.gguf"
    with pytest.raises(FileNotFoundError):
        find_gguf(build, "q5_k_m")


def test_sha256_file(tmp_path: Path) -> None:
    """Known digest of an empty file."""
    p = tmp_path / "e"
    p.write_bytes(b"")
    assert sha256_file(p) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sanity_prompts_cover_both_classes_and_sources() -> None:
    """Five prompts, both classes, all three sources."""
    assert len(SANITY) == 5 and {e for _, _, e in SANITY} == {"SAFE", "INJECTION"}
    assert {s for _, s, _ in SANITY} == {"user_input", "retrieved_chunk", "tool_output"}
