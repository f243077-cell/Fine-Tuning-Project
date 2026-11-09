"""guard-api FastAPI application."""

import logging

from fastapi import Depends, FastAPI, Response, status

from guard.config import Settings, get_settings
from guard.scanner import Scanner, StubScanner
from guard.schemas import HealthResponse

logger = logging.getLogger("guard")

app = FastAPI(title="RU-Guard guard-api")

_scanner: Scanner = StubScanner()


def get_scanner() -> Scanner:
    """Return the active scanner (overridden in tests and in Phase 6)."""
    return _scanner


@app.get("/health", response_model=HealthResponse)
async def health(
    response: Response,
    scanner: Scanner = Depends(get_scanner),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Report whether the scanner backend is reachable."""
    ok = await scanner.healthy()
    if not ok:
        logger.warning("scanner %s is not healthy", scanner.name)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if ok else "unavailable",
        model=settings.guard_model,
        scanner=scanner.name,
        version=settings.version,
    )
