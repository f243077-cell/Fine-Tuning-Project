"""Async Ollama client for the guard model (Architecture.md 6.5)."""

import logging
from typing import Protocol

import httpx

logger = logging.getLogger("guard.ollama")

# Same options as the evaluation harness (evals/baselines.py OLLAMA_OPTIONS), so served and evaluated outputs match.
OLLAMA_OPTIONS = {"temperature": 0, "top_k": 1, "num_predict": 8, "num_ctx": 1024, "seed": 0}


class BackendUnavailable(Exception):
    """Ollama could not be reached or answered with a server error."""


class BackendTimeout(Exception):
    """Ollama did not answer within the timeout."""


class ChatClient(Protocol):
    """Anything that returns the raw model answer for chat messages."""

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Raw assistant text for the messages."""
        ...

    async def healthy(self) -> bool:
        """True when the model is served."""
        ...

    async def aclose(self) -> None:
        """Release network resources."""
        ...


class OllamaClient:
    """Calls POST /api/chat on Ollama with fixed decoding options."""

    def __init__(self, url: str, model: str, timeout: float = 30.0, keep_alive: str = "30m",
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        """Create the HTTP client; transport is for tests."""
        self.model = model
        self.keep_alive = keep_alive
        self._http = httpx.AsyncClient(base_url=url, timeout=httpx.Timeout(timeout, connect=5.0),
                                       transport=transport)

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Raw assistant text; raises BackendTimeout or BackendUnavailable."""
        body = {"model": self.model, "messages": messages, "stream": False,
                "options": OLLAMA_OPTIONS, "keep_alive": self.keep_alive}
        try:
            r = await self._http.post("/api/chat", json=body)
        except httpx.TimeoutException as exc:
            raise BackendTimeout(str(exc) or "timeout") from exc
        except httpx.TransportError as exc:
            raise BackendUnavailable(str(exc) or type(exc).__name__) from exc
        if r.status_code >= 400:
            raise BackendUnavailable(f"ollama HTTP {r.status_code}")
        try:
            return str(r.json()["message"]["content"])
        except (ValueError, KeyError, TypeError) as exc:
            raise BackendUnavailable("malformed ollama response") from exc

    async def healthy(self) -> bool:
        """True when Ollama answers and lists the guard model."""
        try:
            r = await self._http.get("/api/tags", timeout=5.0)
            r.raise_for_status()
            names = {m.get("name") for m in r.json().get("models", [])}
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("ollama health check failed: %s", exc)
            return False
        return self.model in names or f"{self.model}:latest" in names

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()
