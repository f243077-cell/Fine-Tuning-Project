"""Plain helpers for building tiny data fixtures in script tests."""

ATTACKS = ["override", "persona", "prompt_leak", "exfiltration", "tool_abuse"]
SURFACES = ["en", "ru_mix", "ru_pure"]
SOURCES = ["user_input", "retrieved_chunk", "tool_output"]


def make_row(i: int, **kw: object) -> dict:
    """Build one valid DataRow dict with overrides."""
    row = {
        "id": f"r-{i:04d}", "text": f"placeholder text number {i}", "source": "user_input",
        "label": "SAFE", "attack_type": None, "surface": "ru_mix", "origin": "seed",
        "intent_id": None, "hard_negative": False,
    }
    row.update(kw)
    return row


def full_test_rows() -> list[dict]:
    """A small test set that fills every required coverage cell with full triplets."""
    rows: list[dict] = []
    n = 0
    intents: list[dict] = []
    for a in ATTACKS:
        for s in SOURCES:
            intents.append({"label": "INJECTION", "attack_type": a, "source": s})
    for s in SOURCES:
        intents.append({"label": "SAFE", "attack_type": None, "source": s})
        intents.append({"label": "SAFE", "attack_type": None, "source": s, "hard_negative": True})
    for k, intent in enumerate(intents):
        for surface in SURFACES:
            n += 1
            rows.append(make_row(n, origin="test", intent_id=f"t-{k:03d}", surface=surface,
                                 text=f"intent {k} {surface} text", **intent))
    return rows
