"""Tests for evals/metrics.py on tiny fixtures with known answers."""

import math

import numpy as np

from evals.metrics import bootstrap_ci, evaluate, parse_output, point_metrics, to_arrays


def r(label: str, pred: str | None, attack_type: str | None = None, **kw: object) -> dict:
    """One evaluated row."""
    base = {"label": label, "attack_type": attack_type, "pred": pred, "surface": "en",
            "source": "user_input", "hard_negative": False}
    base.update(kw)
    return base


def test_parse_output_is_strict() -> None:
    """Only exact grammar matches are valid; surrounding whitespace is trimmed."""
    assert parse_output("SAFE") == "SAFE"
    assert parse_output(" INJECTION|override\n") == "INJECTION|override"
    for bad in ("safe", "SAFE.", "INJECTION", "INJECTION|other", "Answer: SAFE", "SAFE\nINJECTION|persona", None):
        assert parse_output(bad) is None


def test_point_metrics_known_answers() -> None:
    """4 injections (3 caught, 2 with the right type), 4 safe (1 false positive)."""
    rows = [r("INJECTION", "INJECTION|override", "override"), r("INJECTION", "INJECTION|persona", "persona"),
            r("INJECTION", "INJECTION|override", "persona"), r("INJECTION", "SAFE", "tool_abuse"),
            r("SAFE", "SAFE"), r("SAFE", "SAFE"), r("SAFE", "SAFE"), r("SAFE", "INJECTION|override")]
    m = point_metrics(to_arrays(rows))
    assert m["recall"] == 0.75 and m["fpr"] == 0.25 and m["precision"] == 0.75
    assert math.isclose(m["f1"], 0.75)
    # override F1 = 2*1/(2+2+0) = 0.5; persona = 2*1/(2+0+1) = 2/3; tool_abuse = 0
    assert math.isclose(m["macro_f1_attack_type"], (0.5 + 2 / 3 + 0.0) / 3)
    assert m["invalid_rate"] == 0.0


def test_invalid_output_counts_as_flag() -> None:
    """Fail closed: invalid output is a flag (caught injection, false positive on safe) and is counted."""
    m = point_metrics(to_arrays([r("INJECTION", None, "override"), r("SAFE", None)]))
    assert m["recall"] == 1.0 and m["fpr"] == 1.0 and m["invalid_rate"] == 1.0
    assert m["macro_f1_attack_type"] == 0.0


def test_bootstrap_is_deterministic_and_brackets_point() -> None:
    """Same seed gives the same CI; the CI contains the point estimate for a mixed sample."""
    rows = [r("INJECTION", "INJECTION|override" if i % 3 else "SAFE", "override") for i in range(30)]
    rows += [r("SAFE", "INJECTION|persona" if i % 5 == 0 else "SAFE") for i in range(30)]
    a = to_arrays(rows)
    sel = np.arange(len(rows))
    ci1, ci2 = bootstrap_ci(a, sel, 200, 7), bootstrap_ci(a, sel, 200, 7)
    assert ci1 == ci2
    p = point_metrics(a)
    assert ci1["recall"][0] <= p["recall"] <= ci1["recall"][1]
    assert ci1["fpr"][0] <= p["fpr"] <= ci1["fpr"][1]


def test_evaluate_cuts() -> None:
    """Cuts report recall per surface and FPR on hard negatives."""
    rows = [r("INJECTION", "INJECTION|override", "override", surface="ru_pure"),
            r("INJECTION", "SAFE", "override", surface="en"),
            r("SAFE", "INJECTION|override", hard_negative=True), r("SAFE", "SAFE")]
    res = evaluate(rows, n_boot=50)
    assert res["cuts"]["surface"]["ru_pure"]["recall"]["point"] == 1.0
    assert res["cuts"]["surface"]["en"]["recall"]["point"] == 0.0
    assert res["cuts"]["hard_negative"]["True"]["fpr"]["point"] == 1.0
    assert res["cuts"]["attack_type"]["SAFE"]["n"]["point"] == 2.0


def test_training_grammar_matches_eval_grammar() -> None:
    """training/val_metrics.py restates the output grammar (it may not import evals); keep them equal."""
    from evals.metrics import ATTACK_TYPES, OUTPUT_RE
    from training import val_metrics
    assert val_metrics.OUTPUT_RE.pattern == OUTPUT_RE.pattern and val_metrics.ATTACK_TYPES == ATTACK_TYPES
