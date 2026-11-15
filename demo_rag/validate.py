"""G4 output validation: answer schema, citation presence, canary-token leak (Architecture.md section 12)."""

import re
import secrets

from pydantic import BaseModel, Field

# Accepts [en-02-refund-policy] and the variants small models write, like [doc-id: en-02-refund-policy].
CITATION_RE = re.compile(r"\[\s*(?:doc[-_ ]?id\s*[:=]\s*)?((?:en|ru|p)-[a-z0-9-]+)\s*\]", re.IGNORECASE)
REFUSAL = ("Sorry, I can't answer that safely. Please rephrase your question about Noorbagh products or policies. "
           "(Maaf kijiye, main is ka jawab mehfooz tareeqe se nahi de sakta.)")


def new_canary() -> str:
    """Random canary token placed in the system prompt; it must never appear in an answer."""
    return f"CANARY-{secrets.token_hex(6).upper()}"


class Answer(BaseModel):
    """A validated answer: non-empty text and at least one citation to a document that was in the prompt."""

    text: str = Field(min_length=1)
    citations: list[str] = Field(min_length=1)


class Validation(BaseModel):
    """Result of validating one draft answer."""

    ok: bool
    reason: str | None = None
    answer: Answer | None = None


def citations_in(text: str) -> list[str]:
    """Doc ids cited as [doc-id], in order, without repeats."""
    seen: list[str] = []
    for c in (m.lower() for m in CITATION_RE.findall(text)):
        if c not in seen:
            seen.append(c)
    return seen


def validate_answer(text: str, allowed_doc_ids: set[str], canary: str) -> Validation:
    """Check one draft answer; the first failing rule is the reason."""
    if canary and canary.lower() in text.lower():
        return Validation(ok=False, reason="canary_leak")
    if not text.strip():
        return Validation(ok=False, reason="empty")
    cites = citations_in(text)
    if not cites:
        return Validation(ok=False, reason="no_citation")
    unknown = [c for c in cites if c not in allowed_doc_ids]
    if unknown:
        return Validation(ok=False, reason="unknown_citation")
    return Validation(ok=True, answer=Answer(text=text.strip(), citations=cites))
