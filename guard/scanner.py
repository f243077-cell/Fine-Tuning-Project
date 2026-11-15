"""Scanner: normalize, split into windows, classify each window, combine (Architecture.md 6.2 to 6.4)."""

import asyncio
import logging
import time
from typing import Protocol

from guard.ollama_client import BackendTimeout, BackendUnavailable, ChatClient
from guard.prompt import build_messages, normalize, parse_label
from guard.schemas import AttackType, ScannerError, ScanResult, Verdict
from guard.telemetry import get_tracer

logger = logging.getLogger("guard.scanner")


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
    """Always returns safe; used in unit tests that do not need a model."""

    name = "stub"

    async def scan(self, text: str, source: str) -> ScanResult:
        """Return a safe verdict for any input."""
        return ScanResult(verdict=Verdict.SAFE)

    async def healthy(self) -> bool:
        """The stub is always healthy."""
        return True


def make_windows(text: str, size: int = 1000, overlap: int = 200) -> list[str]:
    """Overlapping character windows covering the text (one window when it fits)."""
    if size <= overlap:
        raise ValueError("window size must be larger than the overlap")
    if len(text) <= size:
        return [text]
    step = size - overlap
    return [text[i:i + size] for i in range(0, max(len(text) - overlap, 1), step)]


_ERROR_PRIORITY = {ScannerError.UNAVAILABLE: 0, ScannerError.TIMEOUT: 1, ScannerError.INVALID_OUTPUT: 2}


class ModelScanner:
    """Scans with the fine-tuned model through a chat client."""

    name = "ollama"

    def __init__(self, client: ChatClient, window_chars: int = 1000, overlap_chars: int = 200,
                 concurrency: int = 2) -> None:
        """Wrap a chat client; concurrency bounds parallel model calls across all requests."""
        self.client = client
        self.window_chars = window_chars
        self.overlap_chars = overlap_chars
        self._sem = asyncio.Semaphore(concurrency)

    async def _call(self, window: str, source: str, index: int) -> tuple[str | None, ScannerError | None]:
        """(label, error) for one window; retries once on any error."""
        messages = build_messages(window, source)
        error: ScannerError | None = None
        for attempt in (1, 2):
            with get_tracer().start_as_current_span("ollama.call") as span:
                span.set_attribute("guard.window_index", index)
                span.set_attribute("guard.attempt", attempt)
                t0 = time.perf_counter()
                try:
                    async with self._sem:
                        raw = await self.client.chat(messages)
                except BackendTimeout:
                    error = ScannerError.TIMEOUT
                except BackendUnavailable:
                    error = ScannerError.UNAVAILABLE
                else:
                    label = parse_label(raw)
                    error = None if label else ScannerError.INVALID_OUTPUT
                    if label:
                        span.set_attribute("guard.latency_ms", round((time.perf_counter() - t0) * 1000, 1))
                        span.set_attribute("guard.label", label)
                        return label, None
                span.set_attribute("guard.latency_ms", round((time.perf_counter() - t0) * 1000, 1))
                span.set_attribute("guard.error", error.value)
            logger.warning("window %d attempt %d failed: %s", index, attempt, error.value)
        return None, error

    async def scan(self, text: str, source: str) -> ScanResult:
        """Any flagged window flags the text; otherwise any error makes it an error; else safe."""
        with get_tracer().start_as_current_span("normalize") as span:
            t0 = time.perf_counter()
            windows = make_windows(normalize(text), self.window_chars, self.overlap_chars)
            span.set_attribute("guard.windows", len(windows))
            span.set_attribute("guard.latency_ms", round((time.perf_counter() - t0) * 1000, 2))
        results = await asyncio.gather(*(self._call(w, source, i) for i, w in enumerate(windows)))
        for label, _ in results:
            if label and label != "SAFE":
                return ScanResult(verdict=Verdict.INJECTION, attack_type=AttackType(label.split("|", 1)[1]),
                                  windows=len(windows))
        errors = [err for _, err in results if err is not None]
        if errors:
            worst = min(errors, key=_ERROR_PRIORITY.__getitem__)
            return ScanResult(verdict=Verdict.ERROR, windows=len(windows), scanner_error=worst)
        return ScanResult(verdict=Verdict.SAFE, windows=len(windows))

    async def healthy(self) -> bool:
        """True when the chat client reports the model is served."""
        return await self.client.healthy()
