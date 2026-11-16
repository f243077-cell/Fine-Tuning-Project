"""Proxy tests with a mock upstream: key added server-side, only playground routes exposed, limits enforced."""
import json
import os

os.environ["PROXY_AUTOSTART"] = "0"

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from deploy.proxy import MAX_BODY_BYTES, ProxySettings, RateLimiter, create_app  # noqa: E402

SECRET = "server-side-key"


def upstream(seen: list[httpx.Request]):
    """Mock guard-api and demo-rag that record each request."""
    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/v1/scan":
            ok = req.headers.get("x-api-key") == SECRET
            return httpx.Response(200 if ok else 401, json={"verdict": "safe"} if ok else {"detail": "bad key"})
        if req.url.path == "/chat/stream":
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  content=b"event: final\ndata: {}\n\n")
        if req.url.path == "/chat":
            return httpx.Response(200, json={"answer": "ok"})
        return httpx.Response(200, json={"status": "ok"})
    return httpx.MockTransport(handle)


def client(tmp_path, seen, **kw) -> TestClient:
    """Proxy with a tiny web build and the mock upstream."""
    (tmp_path / "index.html").write_text("<html>playground</html>", encoding="utf-8")
    s = ProxySettings(guard_api_key=SECRET, web_dir=str(tmp_path), **kw)
    return TestClient(create_app(s, transport=upstream(seen)))


def test_scan_gets_server_key_and_browser_key_is_dropped(tmp_path):
    seen: list[httpx.Request] = []
    r = client(tmp_path, seen).post("/guard/v1/scan", json={"text": "hi", "source": "user_input"},
                                    headers={"X-API-Key": "attacker-key"})
    assert r.status_code == 200 and seen[-1].headers["x-api-key"] == SECRET


def test_key_never_reaches_the_browser(tmp_path):
    r = client(tmp_path, []).post("/guard/v1/scan", json={"text": "hi", "source": "user_input"})
    assert SECRET not in r.text and SECRET not in json.dumps(dict(r.headers))


def test_stats_batch_and_docs_are_not_exposed(tmp_path):
    c = client(tmp_path, [])
    assert c.get("/guard/v1/stats").status_code in (404, 405)
    assert c.post("/guard/v1/scan/batch", json={}).status_code in (404, 405)
    assert c.get("/docs").status_code == 404 or "playground" in c.get("/docs").text


def test_scan_rate_limit_per_visitor(tmp_path):
    c = client(tmp_path, [], scans_per_minute=2)
    a = {"X-Forwarded-For": "1.1.1.1"}
    codes = [c.post("/guard/v1/scan", json={"text": "x", "source": "user_input"}, headers=a).status_code
             for _ in range(3)]
    other = c.post("/guard/v1/scan", json={"text": "x", "source": "user_input"},
                   headers={"X-Forwarded-For": "2.2.2.2"}).status_code
    assert codes == [200, 200, 429] and other == 200


def test_oversized_body_is_413(tmp_path):
    r = client(tmp_path, []).post("/guard/v1/scan", content=b"x" * (MAX_BODY_BYTES + 1))
    assert r.status_code == 413


def test_chat_and_health_are_forwarded(tmp_path):
    seen: list[httpx.Request] = []
    c = client(tmp_path, seen)
    assert c.post("/demo/chat", json={"question": "q", "guard": "on"}).json() == {"answer": "ok"}
    assert c.get("/demo/health").status_code == 200 and c.get("/guard/health").status_code == 200
    assert "x-api-key" not in seen[0].headers


def test_stream_is_passed_through(tmp_path):
    r = client(tmp_path, []).get("/demo/chat/stream", params={"question": "q"})
    assert r.status_code == 200 and "event: final" in r.text


def test_chat_rate_limit(tmp_path):
    c = client(tmp_path, [], chats_per_minute=1)
    assert [c.post("/demo/chat", json={"question": "q"}).status_code for _ in range(2)] == [200, 429]


def test_web_build_is_served(tmp_path):
    assert "playground" in client(tmp_path, []).get("/").text


def test_upstream_down_is_502_without_details(tmp_path):
    def down(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=req)
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    c = TestClient(create_app(ProxySettings(guard_api_key=SECRET, web_dir=str(tmp_path)),
                              transport=httpx.MockTransport(down)))
    r = c.get("/guard/health")
    assert r.status_code == 502 and "refused" not in r.text


def test_rate_limiter_window():
    rl = RateLimiter()
    assert rl.allow("a", "s", 1) and not rl.allow("a", "s", 1) and rl.allow("b", "s", 1)
