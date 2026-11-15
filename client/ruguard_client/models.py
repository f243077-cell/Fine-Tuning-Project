"""Pydantic models for the guard-api HTTP contract (Architecture.md section 7). No imports from the repo."""

from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["user_input", "retrieved_chunk", "tool_output"]
Verdict = Literal["safe", "injection", "error"]
AttackType = Literal["override", "persona", "prompt_leak", "exfiltration", "tool_abuse"]
Action = Literal["allow", "block", "drop_chunk", "redact_tool_output", "log_only"]
ScannerError = Literal["invalid_output", "timeout", "unavailable"]

BLOCK_ACTION: dict[str, Action] = {
    "user_input": "block",
    "retrieved_chunk": "drop_chunk",
    "tool_output": "redact_tool_output",
}


class ScanResult(BaseModel):
    """One scan result from guard-api (or a client-side fail-mode result)."""

    request_id: str
    verdict: Verdict
    attack_type: AttackType | None = None
    action: Action
    model: str
    latency_ms: int
    windows: int
    scanner_error: ScannerError | None = None

    @property
    def flagged(self) -> bool:
        """True when the caller should not use the text as is (any action except allow and log_only)."""
        return self.action not in ("allow", "log_only")


class BatchItem(BaseModel):
    """One text for a batch scan."""

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source: Source
    doc_id: str | None = None


class BatchResult(ScanResult):
    """One batch result, keyed by the item id."""

    id: str


class Health(BaseModel):
    """Body of GET /health."""

    status: str
    model: str
    scanner: str
    version: str


class Stats(BaseModel):
    """Body of GET /v1/stats."""

    total: int
    by_verdict: dict[str, int]
    by_source: dict[str, int]
    by_source_verdict: dict[str, dict[str, int]]
    by_action: dict[str, int]
    quarantined: int
