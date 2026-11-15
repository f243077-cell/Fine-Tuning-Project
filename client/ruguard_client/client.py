"""Sync and async HTTP clients for guard-api (/v1/scan, /v1/scan/batch, /health, /v1/stats).

Retries: transport errors, HTTP 429, and 502/503/504 without a scan body (a proxy or a stopped service) are retried `retries` times with a short backoff.
When guard-api cannot be reached after the retries, `fail_mode` decides:
  "closed" (default): return a result with verdict "error" and the blocking action for the source,
  "open": return the same with action "allow", "raise": raise GuardUnavailable.
A 503 from guard-api already carries a full result (with its own fail-mode action) and is returned as is.
401, 413, and 422 are caller errors and always raise.
"""

import asyncio
import os
import time
import uuid
from collections.abc import Iterable
from typing import Literal

import httpx

from client.ruguard_client.models import (BLOCK_ACTION, BatchItem, BatchResult, Health, ScanResult, Source,
                                          Stats)

FailMode = Literal["closed", "open", "raise"]
_RETRY_STATUS = {429}
_BACKOFF = 0.5


class GuardError(Exception):
    """guard-api rejected the request."""

    def __init__(self, status: int, detail: str) -> None:
        """Keep the HTTP status and the server's detail."""
        super().__init__(f"guard-api HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class GuardAuthError(GuardError):
    """401: missing or wrong API key."""


class GuardRequestTooLarge(GuardError):
    """413: text or batch too large; split it."""


class GuardUnavailable(Exception):
    """guard-api could not be reached (only raised with fail_mode="raise")."""


def _error_for(r: httpx.Response) -> GuardError:
    """Typed error for a non-2xx response that is not a scan result."""
    try:
        detail = str(r.json().get("detail", r.text))
    except ValueError:
        detail = r.text
    if r.status_code == 401:
        return GuardAuthError(401, detail)
    if r.status_code == 413:
        return GuardRequestTooLarge(413, detail)
    return GuardError(r.status_code, detail)


def _fallback(source: str, fail_mode: FailMode, request_id: str) -> ScanResult:
    """Client-side result when guard-api is unreachable."""
    action = "allow" if fail_mode == "open" else BLOCK_ACTION[source]
    return ScanResult(request_id=request_id, verdict="error", attack_type=None, action=action, model="unreachable",
                      latency_ms=0, windows=0, scanner_error="unavailable")


def _is_scan_body(r: httpx.Response) -> bool:
    """True for 200 and for a 503 that carries a scan result body."""
    return r.status_code == 200 or (r.status_code == 503 and ("verdict" in r.text or "results" in r.text))


_GATEWAY_DOWN = {502, 503, 504}


class _Base:
    """Shared configuration."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 120.0, retries: int = 2,
                 fail_mode: FailMode = "closed") -> None:
        """base_url like http://localhost:8001; timeout is per request (a long text has several windows)."""
        if fail_mode not in ("closed", "open", "raise"):
            raise ValueError(f"fail_mode must be closed, open, or raise, got {fail_mode!r}")
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key}
        self.timeout = timeout
        self.retries = retries
        self.fail_mode: FailMode = fail_mode

    @classmethod
    def from_env(cls, **kw):  # type: ignore[no-untyped-def]
        """Build from GUARD_URL and GUARD_API_KEY."""
        return cls(os.environ.get("GUARD_URL", "http://localhost:8001"), os.environ.get("GUARD_API_KEY", ""), **kw)


class GuardClient(_Base):
    """Synchronous guard-api client."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 120.0, retries: int = 2,
                 fail_mode: FailMode = "closed", transport: httpx.BaseTransport | None = None) -> None:
        """Create the client; transport is for tests."""
        super().__init__(base_url, api_key, timeout, retries, fail_mode)
        self._http = httpx.Client(base_url=self.base_url, headers=self.headers, timeout=timeout, transport=transport)

    def _send(self, method: str, path: str, json: dict | None = None) -> httpx.Response | None:
        """Response, or None when unreachable after retries."""
        for attempt in range(self.retries + 1):
            try:
                r = self._http.request(method, path, json=json)
            except httpx.TransportError:
                r = None
            if r is not None and r.status_code in _GATEWAY_DOWN and not _is_scan_body(r) and path != "/health":
                r = None
            if r is not None and r.status_code not in _RETRY_STATUS:
                return r
            if attempt < self.retries:
                time.sleep(_BACKOFF * (attempt + 1))
        if r is not None:
            raise _error_for(r)
        return None

    def scan(self, text: str, source: Source, request_id: str | None = None, doc_id: str | None = None) -> ScanResult:
        """Scan one text."""
        rid = request_id or uuid.uuid4().hex
        body = {"text": text, "source": source, "request_id": rid, "doc_id": doc_id}
        r = self._send("POST", "/v1/scan", body)
        if r is None:
            if self.fail_mode == "raise":
                raise GuardUnavailable(f"guard-api at {self.base_url} is unreachable")
            return _fallback(source, self.fail_mode, rid)
        if not _is_scan_body(r):
            raise _error_for(r)
        return ScanResult.model_validate(r.json())

    def scan_batch(self, items: Iterable[BatchItem | dict], request_id: str | None = None) -> list[BatchResult]:
        """Scan several texts; results keep the item order."""
        objs = [i if isinstance(i, BatchItem) else BatchItem.model_validate(i) for i in items]
        rid = request_id or uuid.uuid4().hex
        r = self._send("POST", "/v1/scan/batch", {"items": [o.model_dump() for o in objs], "request_id": rid})
        if r is None:
            if self.fail_mode == "raise":
                raise GuardUnavailable(f"guard-api at {self.base_url} is unreachable")
            return [BatchResult(id=o.id, **_fallback(o.source, self.fail_mode, f"{rid}:{o.id}").model_dump())
                    for o in objs]
        if not _is_scan_body(r):
            raise _error_for(r)
        return [BatchResult.model_validate(x) for x in r.json()["results"]]

    def health(self) -> Health:
        """GET /health (a 503 body is returned with status "unavailable")."""
        r = self._send("GET", "/health")
        if r is None:
            raise GuardUnavailable(f"guard-api at {self.base_url} is unreachable")
        return Health.model_validate(r.json())

    def stats(self) -> Stats:
        """GET /v1/stats."""
        r = self._send("GET", "/v1/stats")
        if r is None:
            raise GuardUnavailable(f"guard-api at {self.base_url} is unreachable")
        if r.status_code != 200:
            raise _error_for(r)
        return Stats.model_validate(r.json())

    def close(self) -> None:
        """Close the HTTP client."""
        self._http.close()

    def __enter__(self) -> "GuardClient":
        """Context manager."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Close on exit."""
        self.close()


class AsyncGuardClient(_Base):
    """Asynchronous guard-api client (same behaviour as GuardClient)."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 120.0, retries: int = 2,
                 fail_mode: FailMode = "closed", transport: httpx.AsyncBaseTransport | None = None) -> None:
        """Create the client; transport is for tests."""
        super().__init__(base_url, api_key, timeout, retries, fail_mode)
        self._http = httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=timeout,
                                       transport=transport)

    async def _send(self, method: str, path: str, json: dict | None = None) -> httpx.Response | None:
        """Response, or None when unreachable after retries."""
        for attempt in range(self.retries + 1):
            try:
                r = await self._http.request(method, path, json=json)
            except httpx.TransportError:
                r = None
            if r is not None and r.status_code in _GATEWAY_DOWN and not _is_scan_body(r) and path != "/health":
                r = None
            if r is not None and r.status_code not in _RETRY_STATUS:
                return r
            if attempt < self.retries:
                await asyncio.sleep(_BACKOFF * (attempt + 1))
        if r is not None:
            raise _error_for(r)
        return None

    async def scan(self, text: str, source: Source, request_id: str | None = None,
                   doc_id: str | None = None) -> ScanResult:
        """Scan one text."""
        rid = request_id or uuid.uuid4().hex
        r = await self._send("POST", "/v1/scan", {"text": text, "source": source, "request_id": rid, "doc_id": doc_id})
        if r is None:
            if self.fail_mode == "raise":
                raise GuardUnavailable(f"guard-api at {self.base_url} is unreachable")
            return _fallback(source, self.fail_mode, rid)
        if not _is_scan_body(r):
            raise _error_for(r)
        return ScanResult.model_validate(r.json())

    async def scan_batch(self, items: Iterable[BatchItem | dict], request_id: str | None = None) -> list[BatchResult]:
        """Scan several texts; results keep the item order."""
        objs = [i if isinstance(i, BatchItem) else BatchItem.model_validate(i) for i in items]
        rid = request_id or uuid.uuid4().hex
        r = await self._send("POST", "/v1/scan/batch", {"items": [o.model_dump() for o in objs], "request_id": rid})
        if r is None:
            if self.fail_mode == "raise":
                raise GuardUnavailable(f"guard-api at {self.base_url} is unreachable")
            return [BatchResult(id=o.id, **_fallback(o.source, self.fail_mode, f"{rid}:{o.id}").model_dump())
                    for o in objs]
        if not _is_scan_body(r):
            raise _error_for(r)
        return [BatchResult.model_validate(x) for x in r.json()["results"]]

    async def health(self) -> Health:
        """GET /health."""
        r = await self._send("GET", "/health")
        if r is None:
            raise GuardUnavailable(f"guard-api at {self.base_url} is unreachable")
        return Health.model_validate(r.json())

    async def stats(self) -> Stats:
        """GET /v1/stats."""
        r = await self._send("GET", "/v1/stats")
        if r is None:
            raise GuardUnavailable(f"guard-api at {self.base_url} is unreachable")
        if r.status_code != 200:
            raise _error_for(r)
        return Stats.model_validate(r.json())

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncGuardClient":
        """Async context manager."""
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Close on exit."""
        await self.aclose()
