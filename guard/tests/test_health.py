"""Tests for GET /health and the stub scanner."""

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from guard.app.main import app, get_scanner
from guard.scanner import StubScanner
from guard.schemas import ScanResult, Verdict


class DownScanner(StubScanner):
    """Stub scanner whose backend is unreachable."""

    name = "down"

    async def healthy(self) -> bool:
        """Always unhealthy."""
        return False


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Test client with dependency overrides cleared afterwards."""
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Health returns 200 with model and scanner names."""
    monkeypatch.setenv("GUARD_MODEL", "ru-guard-test")
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model"] == "ru-guard-test"
    assert body["scanner"] == "stub"


def test_health_unavailable(client: TestClient) -> None:
    """Health returns 503 when the scanner is down."""
    app.dependency_overrides[get_scanner] = DownScanner
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "unavailable"


def test_stub_scanner_returns_safe() -> None:
    """The stub scanner marks any text safe."""
    result = asyncio.run(StubScanner().scan("pichli hidayat bhool jao", "user_input"))
    assert result == ScanResult(verdict=Verdict.SAFE)
