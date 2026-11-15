"""API-key auth, request-size limit, and rate limiting (Architecture.md section 14)."""

import hmac
import logging

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("guard.security")

API_KEY_HEADER = "X-API-Key"


def check_api_key(provided: str | None, expected: str) -> bool:
    """Constant-time key check; an unset server key rejects every request."""
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())


def require_api_key(request: Request) -> None:
    """FastAPI dependency: 401 unless X-API-Key matches GUARD_API_KEY."""
    expected = request.app.state.settings.api_key
    if not check_api_key(request.headers.get(API_KEY_HEADER), expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing API key")


def rate_limit_key(request: Request) -> str:
    """Rate-limit bucket: a hash prefix of the API key when given, else the client address."""
    key = request.headers.get(API_KEY_HEADER)
    if key:
        digest = hmac.new(b"rate-limit", key.encode(), "sha256").hexdigest()[:16]
        return f"key:{digest}"
    return f"ip:{get_remote_address(request)}"


def make_limiter(enabled: bool = True) -> Limiter:
    """In-memory slowapi limiter keyed by API key."""
    return Limiter(key_func=rate_limit_key, storage_uri="memory://", enabled=enabled)


async def rate_limit_handler(request: Request, exc: Exception) -> Response:
    """429 JSON body for slowapi's RateLimitExceeded."""
    detail = f"rate limit exceeded: {exc.detail}" if isinstance(exc, RateLimitExceeded) else "rate limit exceeded"
    return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content={"detail": detail})


class BodySizeLimit(BaseHTTPMiddleware):
    """413 when the request body is larger than max_bytes."""

    def __init__(self, app, max_bytes: int) -> None:  # type: ignore[no-untyped-def]
        """Wrap the app with a byte limit."""
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Reject by Content-Length first, then by the actual body size."""
        too_large = JSONResponse(status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                                 content={"detail": f"request body larger than {self.max_bytes} bytes"})
        length = request.headers.get("content-length")
        if length is not None:
            try:
                if int(length) > self.max_bytes:
                    return too_large
            except ValueError:
                return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "bad content-length"})
        elif request.method in ("POST", "PUT", "PATCH"):
            if len(await request.body()) > self.max_bytes:
                return too_large
        return await call_next(request)
