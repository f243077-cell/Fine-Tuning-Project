"""OllamaClient tests with httpx.MockTransport (no Ollama needed)."""

import asyncio
import json

import httpx
import pytest

from guard.ollama_client import OLLAMA_OPTIONS, BackendTimeout, BackendUnavailable, OllamaClient


def make(handler) -> OllamaClient:  # type: ignore[no-untyped-def]
    """Client over a mock transport."""
    return OllamaClient("http://ollama:11434", "ru-guard-test", keep_alive="10m",
                        transport=httpx.MockTransport(handler))


def test_chat_sends_fixed_options() -> None:
    """The request carries the model, messages, fixed options, keep_alive, and stream false."""
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        assert req.url.path == "/api/chat"
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "SAFE"}})

    out = asyncio.run(make(handler).chat([{"role": "user", "content": "x"}]))
    assert out == "SAFE"
    assert seen["model"] == "ru-guard-test" and seen["stream"] is False and seen["keep_alive"] == "10m"
    assert seen["options"] == OLLAMA_OPTIONS
    assert OLLAMA_OPTIONS["temperature"] == 0 and OLLAMA_OPTIONS["num_predict"] == 8


@pytest.mark.parametrize("handler,exc", [
    (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), BackendTimeout),
    (lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")), BackendUnavailable),
    (lambda r: httpx.Response(500, text="boom"), BackendUnavailable),
    (lambda r: httpx.Response(200, json={"nope": 1}), BackendUnavailable),
])
def test_chat_errors(handler, exc) -> None:  # type: ignore[no-untyped-def]
    """Timeouts, connection errors, HTTP errors, and bad bodies map to backend exceptions."""
    with pytest.raises(exc):
        asyncio.run(make(handler).chat([]))


@pytest.mark.parametrize("names,ok", [(["ru-guard-test:latest"], True), (["ru-guard-test"], True),
                                      (["other:latest"], False)])
def test_healthy(names: list[str], ok: bool) -> None:
    """Healthy when /api/tags lists the model (with or without :latest)."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": n} for n in names]})

    assert asyncio.run(make(handler).healthy()) is ok


def test_unhealthy_when_down() -> None:
    """Connection errors make the client unhealthy, not crash."""
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    assert asyncio.run(make(handler).healthy()) is False
