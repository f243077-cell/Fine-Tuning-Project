"""guard-api FastAPI application (Architecture.md section 7)."""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from slowapi.errors import RateLimitExceeded

from guard.audit import AuditRow, AuditStore
from guard.config import Settings, get_settings
from guard.ollama_client import ChatClient, OllamaClient
from guard.pii import PiiMasker, get_masker
from guard.policy import decide
from guard.scanner import ModelScanner, Scanner
from guard.schemas import (BatchRequest, BatchResponse, BatchResult, HealthResponse, ScannerError, ScanRequest,
                           ScanResponse, Source, StatsResponse, Verdict)
from guard.security import BodySizeLimit, make_limiter, rate_limit_handler, require_api_key
from guard.telemetry import configure, enable_console, get_tracer

logger = logging.getLogger("guard")

# Scanner errors that mean the model backend is down or too slow: answered with HTTP 503 (body still has the action).
_OUTAGE = {ScannerError.UNAVAILABLE, ScannerError.TIMEOUT}


def get_scanner(request: Request) -> Scanner:
    """The active scanner."""
    return request.app.state.scanner


def get_app_settings(request: Request) -> Settings:
    """The settings the app was built with."""
    return request.app.state.settings


async def scan_text(request: Request, text: str, source: Source, request_id: str,
                    doc_id: str | None = None, chunk_id: str | None = None) -> ScanResponse:
    """Scan one text, apply policy, write the audit row, and quarantine flagged chunks."""
    state = request.app.state
    settings: Settings = state.settings
    tracer = get_tracer()
    t0 = time.perf_counter()
    with tracer.start_as_current_span("scan") as span:
        span.set_attribute("guard.source", source.value)
        span.set_attribute("guard.text_len", len(text))
        result = await state.scanner.scan(text, source.value)
        with tracer.start_as_current_span("policy") as pspan:
            action = decide(result, source, settings.mode, settings.fail_mode)
            pspan.set_attribute("guard.action", action.value)
        latency_ms = int(round((time.perf_counter() - t0) * 1000))
        span.set_attribute("guard.verdict", result.verdict.value)
        span.set_attribute("guard.windows", result.windows)
        span.set_attribute("guard.latency_ms", latency_ms)
        if result.scanner_error:
            span.set_attribute("guard.scanner_error", result.scanner_error.value)
    attack = result.attack_type.value if result.attack_type else None
    row = AuditRow(request_id=request_id, source=source.value, text_hmac=state.audit.hash(text), text_len=len(text),
                   verdict=result.verdict.value, attack_type=attack, action=action.value,
                   model=settings.guard_model, latency_ms=latency_ms)
    await asyncio.to_thread(state.audit.log, row)
    if result.verdict == Verdict.INJECTION and source == Source.RETRIEVED_CHUNK:
        masked = await asyncio.to_thread(state.masker().mask, text)
        await asyncio.to_thread(state.audit.quarantine, masked, attack, doc_id, chunk_id)
    logger.info("scan request_id=%s source=%s len=%d verdict=%s action=%s windows=%d latency_ms=%d error=%s",
                request_id, source.value, len(text), result.verdict.value, action.value, result.windows, latency_ms,
                result.scanner_error.value if result.scanner_error else None)
    return ScanResponse(request_id=request_id, verdict=result.verdict, attack_type=result.attack_type, action=action,
                        model=settings.guard_model, latency_ms=latency_ms, windows=result.windows,
                        scanner_error=result.scanner_error)


def _check_size(text: str, settings: Settings) -> None:
    """413 when one text is longer than MAX_CHARS (the caller must chunk it)."""
    if len(text) > settings.max_chars:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail=f"text longer than {settings.max_chars} characters; split it before scanning")


def create_app(settings: Settings | None = None, chat_client: ChatClient | None = None,
               scanner: Scanner | None = None, masker: Callable[[], PiiMasker] | None = None) -> FastAPI:
    """Build the app; tests pass a stub chat client or scanner, a temp DB path, and optionally a masker."""
    settings = settings or get_settings()
    limiter = make_limiter()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Open the audit DB and the model client; close them on shutdown."""
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per Ollama call is noise
        if not settings.api_key:
            logger.error("GUARD_API_KEY is not set: every /v1 request will get 401")
        configure(settings.otel_exporter, settings.otel_file)
        if settings.otel_console:
            enable_console()
        client = chat_client
        if scanner is None and client is None:
            client = OllamaClient(settings.ollama_url, settings.guard_model, settings.ollama_timeout,
                                  settings.ollama_keep_alive)
        app.state.scanner = scanner or ModelScanner(client, settings.window_chars, settings.overlap_chars,
                                                    settings.concurrency)
        app.state.audit = AuditStore(settings.db_path, settings.audit_salt)
        app.state.masker = masker or get_masker
        await asyncio.to_thread(app.state.masker)  # load spaCy at startup, not on the first flagged chunk
        logger.info("guard-api ready: model=%s mode=%s fail_mode=%s", settings.guard_model, settings.mode,
                    settings.fail_mode)
        try:
            yield
        finally:
            app.state.audit.close()
            if client is not None:
                await client.aclose()

    app = FastAPI(title="RU-Guard guard-api", version=settings.version, lifespan=lifespan)
    app.state.settings = settings
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_middleware(BodySizeLimit, max_bytes=settings.max_body_bytes)
    auth = [Depends(require_api_key)]

    @app.get("/health", response_model=HealthResponse)
    async def health(response: Response, scanner: Scanner = Depends(get_scanner),
                     settings: Settings = Depends(get_app_settings)) -> HealthResponse:
        """Report whether the model backend is reachable (no auth; used by the Docker healthcheck)."""
        ok = await scanner.healthy()
        if not ok:
            logger.warning("scanner %s is not healthy", scanner.name)
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="ok" if ok else "unavailable", model=settings.guard_model,
                              scanner=scanner.name, version=settings.version)

    @app.post("/v1/scan", response_model=ScanResponse, dependencies=auth)
    @limiter.limit(settings.rate_limit)
    async def scan(request: Request, response: Response, body: ScanRequest) -> ScanResponse:
        """Scan one text. 503 (with the fail-mode action in the body) when the model is down or too slow."""
        _check_size(body.text, settings)
        rid = body.request_id or uuid.uuid4().hex
        out = await scan_text(request, body.text, body.source, rid, doc_id=body.doc_id)
        if out.scanner_error in _OUTAGE:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return out

    @app.post("/v1/scan/batch", response_model=BatchResponse, dependencies=auth)
    @limiter.limit(settings.rate_limit)
    async def scan_batch(request: Request, response: Response, body: BatchRequest) -> BatchResponse:
        """Scan several texts (for example retrieved chunks); results keep the item order."""
        if len(body.items) > settings.max_batch_items:
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                                detail=f"more than {settings.max_batch_items} items; split the batch")
        for item in body.items:
            _check_size(item.text, settings)
        rid = body.request_id or uuid.uuid4().hex
        outs = await asyncio.gather(*(
            scan_text(request, it.text, it.source, f"{rid}:{it.id}", doc_id=it.doc_id, chunk_id=it.id)
            for it in body.items))
        if any(o.scanner_error in _OUTAGE for o in outs):
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return BatchResponse(results=[BatchResult(id=it.id, **o.model_dump()) for it, o in zip(body.items, outs)])

    @app.get("/v1/stats", response_model=StatsResponse, dependencies=auth)
    async def stats(request: Request) -> StatsResponse:
        """Counts by verdict, source, and action from the audit log."""
        return StatsResponse(**await asyncio.to_thread(request.app.state.audit.stats))

    return app


app = create_app()
