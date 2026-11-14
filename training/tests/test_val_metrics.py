"""Tests for training/val_metrics.py."""

from collections import Counter

from training.schemas import DataRow
from training.val_metrics import CLASSES, parse_label, stratified_subset, val_metrics


def test_parse_label() -> None:
    """Exact grammar after trimming; placeholders and extras are invalid."""
    assert parse_label(" SAFE\n") == "SAFE" and parse_label("INJECTION|persona") == "INJECTION|persona"
    for bad in ("INJECTION|<attack_type>", "INJECTION", "safe", "SAFE.", "INJECTION|persona extra"):
        assert parse_label(bad) is None


def test_val_metrics_fail_closed() -> None:
    """Invalid output counts as a flag (recall up, FPR up) and as a wrong label for macro-F1."""
    targets = ["SAFE", "SAFE", "INJECTION|override", "INJECTION|persona"]
    m = val_metrics(targets, ["SAFE", "garbage", "INJECTION|override", "INJECTION|<attack_type>"])
    assert m["recall"] == 1.0 and m["fpr"] == 0.5 and m["invalid_rate"] == 0.5 and m["exact_match"] == 0.5
    perfect = val_metrics(targets, targets)
    # SAFE, override, persona score F1 = 1; the 3 absent classes score 0, so macro-F1 = 3/6.
    assert perfect["macro_f1"] == 3 / len(CLASSES) and perfect["fpr"] == 0.0


def test_stratified_subset_is_deterministic_and_balanced() -> None:
    """Same seed, same rows; the label mix follows the full set."""
    rows = [DataRow(id=f"r{i:03d}", text="x", source="user_input", surface="en", origin="synthetic",
                    label="SAFE" if i % 2 else "INJECTION", attack_type=None if i % 2 else "override")
            for i in range(100)]
    a, b = stratified_subset(rows, 20, 7), stratified_subset(rows, 20, 7)
    assert [r.id for r in a] == [r.id for r in b] and len(a) == 20
    assert Counter(r.target for r in a) == {"SAFE": 10, "INJECTION|override": 10}
    assert stratified_subset(rows, 500, 7) == rows
