"""demo-rag FastAPI app on :8002: POST /chat, GET /chat/stream (SSE), GET /health."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from client.ruguard_client import GuardClient
from demo_rag.config import Settings, get_settings
from demo_rag.graph import Deps, RAGState, build_graph, run
from demo_rag.llm import OllamaChat
from demo_rag.store import make_retriever, open_collection

logger = logging.getLogger("demo_rag")


class ChatRequest(BaseModel):
    """Body of POST /chat."""

    question: str = Field(min_length=1, max_length=4000)
    guard: Literal["on", "off"] | None = None


class Source(BaseModel):
    """A cited document."""

    doc_id: str
    title: str


class ChatResponse(BaseModel):
    """Body returned by POST /chat."""

    answer: str
    sources: list[Source]
    blocked: bool
    refused: str | None
    guard: bool
    guard_events: list[dict]
    retrieved: list[str] = []


def guard_flag(settings: Settings, override: str | None) -> bool:
    """GUARD_ENABLED, unless a per-request override is allowed by ALLOW_GUARD_TOGGLE."""
    if override is None:
        return settings.guard_enabled
    if not settings.allow_guard_toggle:
        raise HTTPException(status_code=403, detail="guard override is disabled (ALLOW_GUARD_TOGGLE=false)")
    return override == "on"


def to_response(out: dict, guard: bool) -> ChatResponse:
    """Final graph state as the API body."""
    return ChatResponse(answer=out.get("answer", ""), sources=[Source(**s) for s in out.get("sources", [])],
                        blocked=bool(out.get("blocked")), refused=out.get("refused"), guard=guard,
                        guard_events=out.get("guard_events", []),
                        retrieved=[c["chunk_id"] for c in out.get("chunks", [])])


def create_app(settings: Settings | None = None, deps: Deps | None = None) -> FastAPI:
    """Build the app; tests pass fake dependencies."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Open the vector store, the guard client, and the chat model."""
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        d = deps
        if d is None:
            chat = OllamaChat(settings.ollama_url, settings.chat_model, settings.chat_timeout)
            d = Deps(guard=GuardClient(settings.guard_url, settings.guard_api_key),
                     retrieve=make_retriever(open_collection(settings.chroma_path, settings.collection)),
                     chat=chat, top_k=settings.top_k, context_tokens=settings.context_tokens)
            app.state.chat = chat
        app.state.deps = d
        app.state.graph = build_graph(d)
        logger.info("demo-rag ready: guard_enabled=%s chat_model=%s", settings.guard_enabled, settings.chat_model)
        yield

    app = FastAPI(title="RU-Guard demo-rag", lifespan=lifespan)
    app.state.settings = settings

    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: Request, body: ChatRequest) -> ChatResponse:
        """Answer one question through the guarded graph."""
        guard = guard_flag(settings, body.guard)
        out = await asyncio.to_thread(run, request.app.state.graph, body.question, guard, settings.recursion_limit)
        return to_response(out, guard)

    @app.get("/chat/stream")
    async def chat_stream(request: Request, question: str = Query(min_length=1, max_length=4000),
                          guard: Literal["on", "off"] | None = None) -> StreamingResponse:
        """Server-sent events: one 'step' event per graph node, then a 'final' event with the answer."""
        use_guard = guard_flag(settings, guard)
        graph = request.app.state.graph

        def events() -> Iterator[str]:
            state: RAGState = {"question": question, "guard": use_guard, "guard_events": []}
            final: dict = dict(state)
            for update in graph.stream(state, config={"recursion_limit": settings.recursion_limit},
                                       stream_mode="updates"):
                for node, delta in update.items():
                    delta = delta or {}
                    events_ = delta.get("guard_events") or []
                    final.update({k: v for k, v in delta.items() if k != "guard_events"})
                    final["guard_events"] = final.get("guard_events", []) + events_
                    yield f"event: step\ndata: {json.dumps({'node': node, 'guard_events': events_})}\n\n"
            body = to_response(final, use_guard).model_dump()
            yield f"event: final\ndata: {json.dumps(body, ensure_ascii=False)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/health")
    async def health(request: Request) -> dict:
        """Chat model and guard status."""
        chat_ok = await asyncio.to_thread(request.app.state.chat.healthy) if hasattr(request.app.state, "chat") \
            else True
        guard_ok = True
        if settings.guard_enabled or settings.allow_guard_toggle:
            try:
                h = await asyncio.to_thread(request.app.state.deps.guard.health)
                guard_ok = h.status == "ok"
            except Exception:  # noqa: BLE001 (any failure means not healthy)
                guard_ok = False
        return {"status": "ok" if chat_ok and guard_ok else "degraded", "chat_model": settings.chat_model,
                "chat_model_ok": chat_ok, "guard_enabled": settings.guard_enabled, "guard_ok": guard_ok}

    return app


def _module_app() -> FastAPI:
    """App for `uvicorn demo_rag.app.main:app`."""
    return create_app()


app = _module_app()
