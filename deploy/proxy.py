"""Public front door of the hosted demo (D60): serves the Flutter web build and forwards the playground's calls.

The browser only ever talks to this app. It adds the guard-api key on the server side, so the key is never sent
to a browser; it exposes only the four calls the playground needs (no /v1/stats, no batch); and it limits each
visitor (by the first X-Forwarded-For address) and the number of chat answers running at once.
Logs never contain user text.
"""
import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

logger = logging.getLogger("proxy")
MAX_BODY_BYTES = 64_000  # one scan is at most 12,000 characters; a question at most 4,000


@dataclass(frozen=True)
class ProxySettings:
    """Configuration from environment variables."""

    guard_upstream: str = "http://127.0.0.1:8001"
    demo_upstream: str = "http://127.0.0.1:8002"
    guard_api_key: str = ""
    web_dir: str = "web"
    scans_per_minute: int = 30
    chats_per_minute: int = 6
    chat_concurrency: int = 2

    @classmethod
    def from_env(cls) -> "ProxySettings":
        """Read the settings; GUARD_API_KEY is required."""
        return cls(guard_upstream=os.environ.get("GUARD_UPSTREAM", cls.guard_upstream),
                   demo_upstream=os.environ.get("DEMO_UPSTREAM", cls.demo_upstream),
                   guard_api_key=os.environ.get("GUARD_API_KEY", ""),
                   web_dir=os.environ.get("WEB_DIR", cls.web_dir),
                   scans_per_minute=int(os.environ.get("SCANS_PER_MINUTE", cls.scans_per_minute)),
                   chats_per_minute=int(os.environ.get("CHATS_PER_MINUTE", cls.chats_per_minute)),
                   chat_concurrency=int(os.environ.get("CHAT_CONCURRENCY", cls.chat_concurrency)))


class RateLimiter:
    """Sliding one-minute window per visitor and bucket (in memory; one process)."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, visitor: str, bucket: str, per_minute: int) -> bool:
        """True when this visitor has room left in the bucket, and count the call."""
        now, q = time.monotonic(), self._hits[(visitor, bucket)]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= per_minute:
            return False
        q.append(now)
        return True


def visitor(request: Request) -> str:
    """Client address: the first X-Forwarded-For entry behind the hosting proxy, else the socket peer."""
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


async def body_of(request: Request) -> bytes:
    """Request body, refused when larger than MAX_BODY_BYTES."""
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="request too large")
    return body


def create_app(settings: ProxySettings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """Build the proxy; tests pass a mock transport instead of the real upstream services."""
    s = settings or ProxySettings.from_env()
    if not s.guard_api_key:
        logger.error("GUARD_API_KEY is not set: every scan will get 401 from guard-api")
    http = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(300.0, connect=10.0))
    limits, chats = RateLimiter(), asyncio.Semaphore(s.chat_concurrency)
    app = FastAPI(title="RU-Guard demo proxy", docs_url=None, redoc_url=None, openapi_url=None)

    def limited(request: Request, bucket: str, per_minute: int) -> None:
        """429 when the visitor is over the limit."""
        if not limits.allow(visitor(request), bucket, per_minute):
            raise HTTPException(status_code=429, detail="too many requests; wait a minute")

    def relay(r: httpx.Response) -> Response:
        """Upstream answer back to the browser (body and status only)."""
        return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))

    @app.get("/guard/health")
    async def guard_health() -> Response:
        """guard-api health (no key needed)."""
        return relay(await http.get(f"{s.guard_upstream}/health"))

    @app.post("/guard/v1/scan")
    async def scan(request: Request) -> Response:
        """Scan one text; the key is added here and any key sent by the browser is dropped."""
        limited(request, "scan", s.scans_per_minute)
        body = await body_of(request)
        r = await http.post(f"{s.guard_upstream}/v1/scan", content=body,
                            headers={"Content-Type": "application/json", "X-API-Key": s.guard_api_key})
        return relay(r)

    @app.get("/demo/health")
    async def demo_health() -> Response:
        """demo-rag health."""
        return relay(await http.get(f"{s.demo_upstream}/health"))

    async def chat_slot() -> None:
        """Take one of the chat slots, or 503 when all are busy (the CPU answers one question at a time)."""
        try:
            await asyncio.wait_for(chats.acquire(), timeout=5)
        except TimeoutError:
            raise HTTPException(status_code=503, detail="the demo is busy answering others; try again shortly")

    @app.post("/demo/chat")
    async def chat(request: Request) -> Response:
        """One question through the guarded RAG pipeline."""
        limited(request, "chat", s.chats_per_minute)
        body = await body_of(request)
        await chat_slot()
        try:
            r = await http.post(f"{s.demo_upstream}/chat", content=body, headers={"Content-Type": "application/json"})
        finally:
            chats.release()
        return relay(r)

    @app.get("/demo/chat/stream")
    async def chat_stream(request: Request) -> Response:
        """Server-sent events from demo-rag, passed through as they arrive."""
        limited(request, "chat", s.chats_per_minute)
        await chat_slot()
        try:
            up = await http.send(http.build_request("GET", f"{s.demo_upstream}/chat/stream",
                                                    params=dict(request.query_params)), stream=True)
        except Exception:
            chats.release()
            raise

        async def done() -> None:
            """Close the upstream stream and free the slot."""
            await up.aclose()
            chats.release()

        return StreamingResponse(up.aiter_bytes(),  # decoded: Content-Encoding is not passed on
                                 status_code=up.status_code,
                                 media_type=up.headers.get("content-type", "text/event-stream"),
                                 background=BackgroundTask(done))

    @app.exception_handler(httpx.HTTPError)
    async def upstream_down(_: Request, exc: httpx.HTTPError) -> JSONResponse:
        """Upstream unreachable or too slow: 502 without internal details."""
        logger.warning("upstream error: %s", type(exc).__name__)
        return JSONResponse({"detail": "the service is starting or busy; try again shortly"}, status_code=502)

    web = Path(s.web_dir)
    if web.is_dir():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    else:
        logger.warning("web build not found at %s; only the API routes are served", web)
    return app


app = create_app() if os.environ.get("PROXY_AUTOSTART", "1") == "1" else None
