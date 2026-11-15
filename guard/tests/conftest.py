"""Shared fixtures: a scripted fake Ollama chat client and an app factory with a temp DB."""

import asyncio
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from guard.app.main import create_app
from guard.config import Settings
from guard.ollama_client import BackendTimeout, BackendUnavailable

API_KEY = "test-key"


class FakeChat:
    """Answers by keyword in the user message; records every call. No model needed."""

    def __init__(self, script: list[str] | None = None, delay: float = 0.0) -> None:
        """script: answers returned in order before keyword rules apply."""
        self.calls: list[list[dict[str, str]]] = []
        self.script = list(script or [])
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.up = True

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Scripted answer, or a keyword rule on the user text."""
        self.calls.append(messages)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.script:
                return self.script.pop(0)
            text = messages[-1]["content"]
            if "backend_down" in text:
                raise BackendUnavailable("connection refused")
            if "backend_slow" in text:
                raise BackendTimeout("read timeout")
            if "garbage_out" in text:
                return "Sure! Here is the system prompt"
            if "bhool jao" in text or "ignore previous" in text:
                return "INJECTION|override"
            if "system prompt dikhao" in text:
                return "INJECTION|prompt_leak"
            return "SAFE"
        finally:
            self.active -= 1

    async def healthy(self) -> bool:
        """Configurable health."""
        return self.up

    async def aclose(self) -> None:
        """Nothing to close."""


def make_settings(tmp_path: Path, **overrides) -> Settings:
    """Test settings: temp DB, fixed key and salt, small limits."""
    base = Settings(guard_model="ru-guard-test", api_key=API_KEY, audit_salt="test-salt",
                    db_path=str(tmp_path / "guard.db"), rate_limit="1000/minute")
    return replace(base, **overrides)


@pytest.fixture
def fake_chat() -> FakeChat:
    """A fresh fake chat client."""
    return FakeChat()


@pytest.fixture
def app_client(tmp_path: Path, fake_chat: FakeChat) -> Callable[..., TestClient]:
    """Factory: app_client(**settings overrides) -> started TestClient (closed after the test)."""
    clients: list[TestClient] = []

    def build(chat: FakeChat | None = None, **overrides) -> TestClient:
        app = create_app(make_settings(tmp_path, **overrides), chat_client=chat or fake_chat)
        c = TestClient(app, headers={"X-API-Key": API_KEY})
        c.__enter__()
        clients.append(c)
        return c

    yield build
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(app_client: Callable[..., TestClient]) -> Iterator[TestClient]:
    """Default started client."""
    yield app_client()
