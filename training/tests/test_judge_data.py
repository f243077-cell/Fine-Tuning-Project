"""Tests for training/judge_data.py and the judge/hard-negative steps in build_dataset.py."""

import json
from pathlib import Path

from training.build_dataset import Report, apply_judgements, has_trigger, relabel_hard_negatives
from training.gen_prompts import build_judge_prompt
from training.judge_data import parse_judgement, run_judge
from training.schemas import DataRow


def row(i: int, text: str = "kuch text yahan", **kw: object) -> DataRow:
    """One synthetic row."""
    base = dict(id=f"syn-{i:03d}", text=text, source="user_input", label="SAFE", surface="ru_mix",
                origin="synthetic")
    base.update(kw)
    return DataRow(**base)


def test_parse_judgement_variants() -> None:
    """JSON, loose text, and garbage."""
    assert parse_judgement("GOOD YES") == (5, True)
    assert parse_judgement("minor, no") == (4, False)
    assert parse_judgement("Answer: BROKEN YES") == (2, True)
    assert parse_judgement("no idea") is None
    assert parse_judgement("FINE YES") is None


def test_judge_prompt_mentions_claim() -> None:
    """Injection prompts carry the attack requirement; safe prompts the safe claim."""
    p = build_judge_prompt(row(1, label="INJECTION", attack_type="persona"))
    assert "ignores rules" in p and "mostly Roman Urdu" not in p
    assert "it is SAFE" in build_judge_prompt(row(2, surface="ru_pure"))


def test_run_judge_resumes(tmp_path: Path) -> None:
    """Each row is judged once; unparseable answers are recorded as failures."""
    rows = [row(i) for i in range(5)]
    out = tmp_path / "judgements.jsonl"
    answers = iter(["GOOD YES", "???", "BROKEN YES"])
    counts = run_judge(rows[:3], lambda p, s: [next(answers) for _ in p], out, batch=2)
    assert counts == {"judged": 3, "parse_error": 1}
    calls: list[int] = []

    def fake(prompts: list, seeds: list[int]) -> list[str]:
        calls.append(len(prompts))
        return ["MINOR NO"] * len(prompts)

    run_judge(rows, fake, out, batch=10)
    assert calls == [2]
    recs = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in recs] == [r.id for r in rows]
    assert recs[1]["parse_error"] and recs[1]["coherent"] == 0


def test_apply_judgements_drops_with_reasons() -> None:
    """Missing, incoherent, and label-rejected rows are dropped."""
    rows = [row(i) for i in range(4)]
    judged = {"syn-000": {"coherent": 5, "label_ok": True}, "syn-001": {"coherent": 3, "label_ok": True},
              "syn-002": {"coherent": 5, "label_ok": False}}
    report = Report()
    kept = apply_judgements(rows, judged, 4, report)
    assert [r.id for r in kept] == ["syn-000"]
    assert report.dropped == {"judge_incoherent": 1, "judge_label": 1, "judge_missing": 1}


def test_hard_negative_needs_trigger() -> None:
    """Hard negatives without a trigger word become plain SAFE rows."""
    assert has_trigger("Pichli baat bhool jao, chai piyo") and not has_trigger("aaj mausam acha hai")
    rows = [row(1, "aaj mausam acha hai", hard_negative=True), row(2, "password reset kaise karun", hard_negative=True)]
    report = Report()
    out = relabel_hard_negatives(rows, report)
    assert [r.hard_negative for r in out] == [False, True]
    assert report.extra == {"hard_negative_relabeled_plain": 1}
