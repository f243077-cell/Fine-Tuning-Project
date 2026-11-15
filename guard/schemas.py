"""Pydantic models for guard-api inputs and outputs (Architecture.md section 7)."""

from enum import StrEnum

from pydantic import BaseModel, Field


class Source(StrEnum):
    """Where the scanned text came from."""

    USER_INPUT = "user_input"
    RETRIEVED_CHUNK = "retrieved_chunk"
    TOOL_OUTPUT = "tool_output"


class Verdict(StrEnum):
    """Scan verdict."""

    SAFE = "safe"
    INJECTION = "injection"
    ERROR = "error"


class AttackType(StrEnum):
    """Attack families in the output grammar (Architecture.md 6.4)."""

    OVERRIDE = "override"
    PERSONA = "persona"
    PROMPT_LEAK = "prompt_leak"
    EXFILTRATION = "exfiltration"
    TOOL_ABUSE = "tool_abuse"


class Action(StrEnum):
    """What the caller should do with the text (Architecture.md section 8)."""

    ALLOW = "allow"
    BLOCK = "block"
    DROP_CHUNK = "drop_chunk"
    REDACT_TOOL_OUTPUT = "redact_tool_output"
    LOG_ONLY = "log_only"


class ScannerError(StrEnum):
    """Why a scan could not produce a valid label."""

    INVALID_OUTPUT = "invalid_output"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


class ScanResult(BaseModel):
    """Result of scanning one text with a scanner (all windows combined)."""

    verdict: Verdict
    attack_type: AttackType | None = None
    windows: int = 1
    scanner_error: ScannerError | None = None


class ScanRequest(BaseModel):
    """Body of POST /v1/scan."""

    text: str = Field(min_length=1)
    source: Source
    request_id: str | None = Field(default=None, max_length=128)
    doc_id: str | None = Field(default=None, max_length=256)


class ScanResponse(BaseModel):
    """Body returned for one scanned text."""

    request_id: str
    verdict: Verdict
    attack_type: AttackType | None
    action: Action
    model: str
    latency_ms: int
    windows: int
    scanner_error: ScannerError | None


class BatchItem(BaseModel):
    """One item of POST /v1/scan/batch."""

    id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1)
    source: Source
    doc_id: str | None = Field(default=None, max_length=256)


class BatchRequest(BaseModel):
    """Body of POST /v1/scan/batch."""

    items: list[BatchItem] = Field(min_length=1)
    request_id: str | None = Field(default=None, max_length=128)


class BatchResult(ScanResponse):
    """One result of a batch scan, keyed by the item id."""

    id: str


class BatchResponse(BaseModel):
    """Body of POST /v1/scan/batch."""

    results: list[BatchResult]


class HealthResponse(BaseModel):
    """Body of GET /health."""

    status: str
    model: str
    scanner: str
    version: str


class StatsResponse(BaseModel):
    """Body of GET /v1/stats: counts from the audit log."""

    total: int
    by_verdict: dict[str, int]
    by_source: dict[str, int]
    by_source_verdict: dict[str, dict[str, int]]
    by_action: dict[str, int]
    quarantined: int
