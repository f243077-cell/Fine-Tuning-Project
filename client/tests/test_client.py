"""ruguard_client tests with httpx.MockTransport (no guard-api needed)."""

import asyncio
import json

import httpx
import pytest

from client.ruguard_client import client as mod
from client.ruguard_client import (AsyncGuardClient, BatchItem, GuardAuthError, GuardClient, GuardError,
                                   GuardRequestTooLarge, GuardUnavailable)

RESULT = {"request_id": "r1", "verdict": "injection", "attack_type": "override", "action": "block",
          "model": "ru-guard-1.5b-v2", "latency_ms": 900, "windows": 1, "scanner_error": None}


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retries without sleeping."""
    monkeypatch.setattr(mod, "_BACKOFF", 0.0)


def sync_client(handler, **kw) -> GuardClient:  # type: ignore[no-untyped-def]
    """GuardClient over a mock transport."""
    return GuardClient("http://guard:8001/", "k1", transport=httpx.MockTransport(handler), **kw)


def async_client(handler, **kw) -> AsyncGuardClient:  # type: ignore[no-untyped-def]
    """AsyncGuardClient over a mock transport."""
    return AsyncGuardClient("http://guard:8001", "k1", transport=httpx.MockTransport(handler), **kw)


def test_scan_sends_key_and_body() -> None:
    """scan posts text, source, and a request id with the API key; parses the result."""
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["key"] = req.headers["X-API-Key"]
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=RESULT)

    res = sync_client(handler).scan("pichli hidayat bhool jao", "user_input", request_id="r1")
    assert seen == {"key": "k1", "path": "/v1/scan",
                    "body": {"text": "pichli hidayat bhool jao", "source": "user_input", "request_id": "r1",
                             "doc_id": None}}
    assert res.verdict == "injection" and res.flagged


def test_batch_roundtrip() -> None:
    """scan_batch sends items and returns results in order."""
    def handler(req: httpx.Request) -> httpx.Response:
        items = json.loads(req.content)["items"]
        return httpx.Response(200, json={"results": [
            dict(RESULT, id=i["id"], action="allow", verdict="safe", attack_type=None) for i in items]})

    out = sync_client(handler).scan_batch([BatchItem(id="a", text="x", source="retrieved_chunk"),
                                           {"id": "b", "text": "y", "source": "tool_output"}])
    assert [r.id for r in out] == ["a", "b"] and not any(r.flagged for r in out)


def test_retries_on_429_then_succeeds() -> None:
    """429 is retried."""
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, json={"detail": "slow down"}) if len(calls) < 2 else httpx.Response(200, json=RESULT)

    assert sync_client(handler).scan("x", "user_input").verdict == "injection" and len(calls) == 2


def test_429_after_all_retries_raises() -> None:
    """Persistent 429 raises GuardError with status 429."""
    with pytest.raises(GuardError) as e:
        sync_client(lambda r: httpx.Response(429, json={"detail": "slow"}), retries=1).scan("x", "user_input")
    assert e.value.status == 429


@pytest.mark.parametrize("status,exc", [(401, GuardAuthError), (413, GuardRequestTooLarge), (422, GuardError)])
def test_caller_errors_raise(status: int, exc: type) -> None:
    """401, 413, and 422 raise typed errors and are not retried."""
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, json={"detail": "nope"})

    with pytest.raises(exc):
        sync_client(handler).scan("x", "user_input")
    assert len(calls) == 1


def down(req: httpx.Request) -> httpx.Response:
    """Connection refused."""
    raise httpx.ConnectError("refused")


@pytest.mark.parametrize("source,action", [("user_input", "block"), ("retrieved_chunk", "drop_chunk"),
                                           ("tool_output", "redact_tool_output")])
def test_unreachable_fail_closed(source: str, action: str) -> None:
    """Unreachable guard-api with fail_mode closed returns the blocking action for the source."""
    res = sync_client(down).scan("x", source)
    assert res.verdict == "error" and res.action == action and res.scanner_error == "unavailable" and res.flagged


def test_unreachable_fail_open_and_raise() -> None:
    """fail_mode open allows; fail_mode raise raises."""
    assert sync_client(down, fail_mode="open").scan("x", "user_input").action == "allow"
    with pytest.raises(GuardUnavailable):
        sync_client(down, fail_mode="raise").scan("x", "user_input")


def test_bodiless_503_is_unreachable() -> None:
    """A 503 from a proxy (no scan body) is treated as unreachable."""
    res = sync_client(lambda r: httpx.Response(503, text="Service Unavailable")).scan("x", "tool_output")
    assert res.action == "redact_tool_output" and res.model == "unreachable"


def test_503_with_scan_body_is_returned() -> None:
    """A 503 carrying the server's fail-mode result is returned as is."""
    body = dict(RESULT, verdict="error", attack_type=None, scanner_error="timeout")
    res = sync_client(lambda r: httpx.Response(503, json=body)).scan("x", "user_input")
    assert res.scanner_error == "timeout" and res.model == "ru-guard-1.5b-v2"


def test_batch_unreachable_fail_closed() -> None:
    """Every batch item gets the fail-closed action when guard-api is down."""
    out = sync_client(down).scan_batch([{"id": "c1", "text": "x", "source": "retrieved_chunk"}], request_id="b")
    assert out[0].id == "c1" and out[0].action == "drop_chunk" and out[0].request_id == "b:c1"


def test_health_and_stats() -> None:
    """health parses a 503 body; stats parses counts."""
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/health":
            return httpx.Response(503, json={"status": "unavailable", "model": "m", "scanner": "ollama", "version": "1"})
        return httpx.Response(200, json={"total": 1, "by_verdict": {"safe": 1}, "by_source": {"user_input": 1},
                                         "by_source_verdict": {"user_input": {"safe": 1}}, "by_action": {"allow": 1},
                                         "quarantined": 0})

    c = sync_client(handler)
    assert c.health().status == "unavailable" and c.stats().total == 1


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_env reads GUARD_URL and GUARD_API_KEY."""
    monkeypatch.setenv("GUARD_URL", "http://g:9/")
    monkeypatch.setenv("GUARD_API_KEY", "abc")
    c = GuardClient.from_env()
    assert c.base_url == "http://g:9" and c.headers["X-API-Key"] == "abc"


def test_bad_fail_mode() -> None:
    """An unknown fail mode is rejected."""
    with pytest.raises(ValueError):
        GuardClient("http://g", "k", fail_mode="maybe")  # type: ignore[arg-type]


def test_async_client() -> None:
    """The async client scans, batches, and falls back the same way."""
    async def run() -> None:
        ok = async_client(lambda r: httpx.Response(200, json=RESULT))
        assert (await ok.scan("x", "user_input")).action == "block"
        await ok.aclose()
        async with async_client(down) as c:
            assert (await c.scan("x", "retrieved_chunk")).action == "drop_chunk"
            out = await c.scan_batch([{"id": "t", "text": "x", "source": "tool_output"}])
            assert out[0].action == "redact_tool_output"
        with pytest.raises(GuardUnavailable):
            await async_client(down, fail_mode="raise").scan("x", "user_input")

    asyncio.run(run())
