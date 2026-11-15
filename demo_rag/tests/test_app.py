"""demo-rag API tests with fake dependencies."""

import json
from dataclasses import replace

from fastapi.testclient import TestClient

from demo_rag.app.main import create_app
from demo_rag.config import Settings
from demo_rag.graph import Deps
from demo_rag.tests.fakes import ExplodingGuard, FakeGuard, ScriptedChat, fake_retrieve


def client(guard=None, **kw) -> TestClient:  # type: ignore[no-untyped-def]
    """Started client over fakes."""
    settings = replace(Settings(), **kw)
    deps = Deps(guard=guard or FakeGuard(), retrieve=fake_retrieve, chat=ScriptedChat())
    c = TestClient(create_app(settings, deps))
    c.__enter__()
    return c


def test_chat_answers_with_sources() -> None:
    """POST /chat returns the answer, sources, and guard events."""
    r = client().post("/chat", json={"question": "What is the refund window?"})
    assert r.status_code == 200
    body = r.json()
    assert body["sources"][0]["doc_id"] == "en-02-refund-policy" and body["guard"] is True
    assert {e["checkpoint"] for e in body["guard_events"]} == {"G1", "G2", "G4"}


def test_override_needs_allow_guard_toggle() -> None:
    """guard=off is refused unless ALLOW_GUARD_TOGGLE=true."""
    assert client().post("/chat", json={"question": "q", "guard": "off"}).status_code == 403
    c = client(guard=ExplodingGuard(), allow_guard_toggle=True)
    body = c.post("/chat", json={"question": "q", "guard": "off"}).json()
    assert body["guard"] is False and body["guard_events"] == []


def test_guard_disabled_by_config_makes_no_calls() -> None:
    """GUARD_ENABLED=false: no guard calls at all."""
    body = client(guard=ExplodingGuard(), guard_enabled=False).post("/chat", json={"question": "q"}).json()
    assert body["guard"] is False


def test_stream_sends_steps_then_final() -> None:
    """GET /chat/stream emits step events per node and a final answer event."""
    c = client()
    with c.stream("GET", "/chat/stream", params={"question": "What is the refund window?"}) as r:
        text = "".join(r.iter_text())
    events = [blk for blk in text.split("\n\n") if blk.strip()]
    names = [e.split("\n")[0] for e in events]
    assert names[-1] == "event: final" and names.count("event: step") >= 5
    final = json.loads(events[-1].split("data: ", 1)[1])
    assert final["sources"][0]["doc_id"] == "en-02-refund-policy"


def test_health() -> None:
    """Health reports guard and chat status."""
    body = client().get("/health").json()
    assert body["status"] == "ok" and body["guard_ok"] is True
