"""Tests for training/generate_data.py (no model: a fake generate function)."""

import json
from pathlib import Path

import pytest

from training.generate_data import (
    Cell, GenerateConfig, allocate, build_prompt, dry_run, load_config, parse_items, plan_cells, run,
)
from training.jsonl import read_rows
from training.schemas import DataRow

REPO = Path(__file__).resolve().parents[2]


def small_cfg(**kw: object) -> GenerateConfig:
    """Tiny config for fast tests."""
    base = dict(raw_total=60, items_per_call=5, batch_prompts=8, shots=2,
                surface_share={"en": 0.2, "ru_mix": 0.4, "ru_pure": 0.4},
                source_share={"user_input": 0.5, "retrieved_chunk": 0.25, "tool_output": 0.25})
    base.update(kw)
    return GenerateConfig.model_validate(base)


def seed_rows() -> list[DataRow]:
    """A few seeds covering every category."""
    rows = []
    for i, a in enumerate(["override", "persona", "prompt_leak", "exfiltration", "tool_abuse"]):
        rows.append(DataRow(id=f"s{i}", text=f"seed injection {a}", source="user_input", label="INJECTION",
                            attack_type=a, surface="ru_mix", origin="seed"))
    rows.append(DataRow(id="s5", text="seed hard negative", source="user_input", label="SAFE",
                        surface="ru_mix", origin="seed", hard_negative=True))
    rows.append(DataRow(id="s6", text="seed plain", source="tool_output", label="SAFE",
                        surface="ru_pure", origin="seed"))
    return rows


def fake_generate(prompts: list, seeds: list[int]) -> list[str]:
    """Return 5 distinct items per prompt, keyed by the sampling seed."""
    return [json.dumps([f"item {s} number {k}" for k in range(5)]) for s in seeds]


def test_allocate_sums_and_rounds() -> None:
    """Largest remainder keeps the exact total."""
    out = allocate(10, {"a": 1, "b": 1, "c": 1})
    assert sum(out.values()) == 10
    assert sorted(out.values()) == [3, 3, 4]


def test_plan_cells_repo_config() -> None:
    """The real config plans 63 cells with the PRD mix."""
    cfg = load_config(REPO / "training/configs/generate.yaml")
    cells = plan_cells(cfg)
    total = sum(c.target for c in cells)
    assert len(cells) == 63 and total == cfg.raw_total
    inj = sum(c.target for c in cells if c.label == "INJECTION")
    hn = sum(c.target for c in cells if c.hard_negative)
    en = sum(c.target for c in cells if c.surface == "en")
    assert inj == total // 2
    assert hn == pytest.approx(total * 0.25, abs=2)
    assert en / total == pytest.approx(0.15, abs=0.01)
    assert len({c.key for c in cells}) == len(cells)


def test_plan_cells_rejects_bad_keys() -> None:
    """Share keys must match the enums exactly."""
    with pytest.raises(ValueError):
        plan_cells(small_cfg(surface_share={"en": 1.0}))


def test_build_prompt_deterministic_and_on_category() -> None:
    """Same attempt gives the same prompt; examples come from the cell's category."""
    cfg = small_cfg()
    cell = Cell("INJECTION", "persona", "ru_pure", "user_input", False, 10)
    a, sa = build_prompt(cell, seed_rows(), cfg, 0)
    b, sb = build_prompt(cell, seed_rows(), cfg, 0)
    c, sc = build_prompt(cell, seed_rows(), cfg, 1)
    assert a == b and sa == sb and sc != sa
    assert "seed injection persona" in a[1]["content"]
    assert "seed injection override" not in a[1]["content"]
    assert a[0]["role"] == "system" and "harmless" in a[0]["content"]


def test_parse_items_variants() -> None:
    """JSON arrays (with prose or fences), objects, and numbered-line fallback."""
    assert parse_items('Sure:\n```json\n["one item here", "two item here"]\n```') == ["one item here", "two item here"]
    assert parse_items('[{"status": "ok", "note": "x"}]') == ['{"status": "ok", "note": "x"}']
    assert parse_items("1. pehla misaal yahan hai\n2. doosri misaal yahan hai") == [
        "pehla misaal yahan hai", "doosri misaal yahan hai"]
    assert parse_items('["same text again", "same text again"]') == ["same text again"]
    assert parse_items("") == []


def test_run_reaches_targets_and_resumes(tmp_path: Path) -> None:
    """Every cell reaches its target; a second run makes no calls; ids are unique."""
    cfg = small_cfg()
    counts = run(cfg, seed_rows(), fake_generate, tmp_path)
    assert counts == {c.key: c.target for c in plan_cells(cfg)}
    calls: list[int] = []

    def counting(prompts: list, seeds: list[int]) -> list[str]:
        calls.append(len(prompts))
        return fake_generate(prompts, seeds)

    assert run(cfg, seed_rows(), counting, tmp_path) == counts
    assert calls == []
    ids = []
    for shard in (tmp_path / "shards").glob("*.jsonl"):
        rows, errors = read_rows(shard)
        assert errors == []
        ids += [r.id for r in rows]
        assert all(r.origin == "synthetic" for r in rows)
    assert len(ids) == len(set(ids)) == cfg.raw_total


def test_run_stops_on_attempt_cap(tmp_path: Path) -> None:
    """A generator that returns nothing usable ends at the attempt cap, not in a loop."""
    cfg = small_cfg(max_attempt_factor=2.0)
    counts = run(cfg, seed_rows(), lambda p, s: ["no json"] * len(p), tmp_path)
    assert sum(counts.values()) == 0


def test_run_max_calls(tmp_path: Path) -> None:
    """--max-calls limits the number of generation calls."""
    cfg = small_cfg()
    counts = run(cfg, seed_rows(), fake_generate, tmp_path, max_calls=2)
    assert sum(counts.values()) <= 10


def test_dry_run_writes_preview(tmp_path: Path) -> None:
    """Dry run writes prompts without a model."""
    path = dry_run(small_cfg(), seed_rows(), tmp_path, 3)
    assert path.read_text(encoding="utf-8").count("=====") == 3
