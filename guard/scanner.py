"""Scanner interface and the stub scanner used until the real model is wired in (Phase 6)."""

from typing import Protocol

from guard.schemas import ScanResult, Verdict


class Scanner(Protocol):
    """Anything that can classify a text for a given source."""

    name: str

    async def scan(self, text: str, source: str) -> ScanResult:
        """Classify one text."""
        ...

    async def healthy(self) -> bool:
        """Return True when the backing model is reachable."""
        ...


class StubScanner:
    """Always returns safe; used in unit tests and before the model exists."""

    name = "stub"

    async def scan(self, text: str, source: str) -> ScanResult:
        """Return a safe verdict for any input."""
        return ScanResult(verdict=Verdict.SAFE)

    async def healthy(self) -> bool:
        """The stub is always healthy."""
        return True
