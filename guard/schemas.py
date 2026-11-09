"""Pydantic models for guard-api inputs and outputs."""

from enum import StrEnum

from pydantic import BaseModel


class Verdict(StrEnum):
    """Scan verdict."""

    SAFE = "safe"
    INJECTION = "injection"
    ERROR = "error"


class ScanResult(BaseModel):
    """Result of scanning one text with a scanner."""

    verdict: Verdict
    attack_type: str | None = None


class HealthResponse(BaseModel):
    """Body of GET /health."""

    status: str
    model: str
    scanner: str
    version: str
