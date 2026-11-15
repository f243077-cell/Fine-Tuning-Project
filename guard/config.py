"""Service configuration read from environment variables."""

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    """Integer environment variable with a default."""
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    """Float environment variable with a default."""
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    """guard-api settings (Architecture.md sections 6.2, 6.5, 7, 8, 14)."""

    guard_model: str = "ru-guard-1.5b-v2"
    version: str = "0.6.0"
    ollama_url: str = "http://localhost:11434"
    ollama_timeout: float = 30.0
    ollama_keep_alive: str = "30m"
    api_key: str = ""
    audit_salt: str = ""
    db_path: str = "guard.db"
    fail_mode: str = "closed"
    mode: str = "enforce"
    window_chars: int = 1000
    overlap_chars: int = 200
    max_chars: int = 12000
    max_batch_items: int = 32
    max_body_bytes: int = 2_000_000
    concurrency: int = 2
    rate_limit: str = "120/minute"
    otel_console: bool = False
    otel_exporter: str = "file"
    otel_file: str = "traces.jsonl"


def get_settings() -> Settings:
    """Build settings from the environment."""
    fail_mode = os.environ.get("FAIL_MODE", "closed").strip().lower()
    mode = os.environ.get("MODE", "enforce").strip().lower()
    if fail_mode not in ("closed", "open"):
        raise ValueError(f"FAIL_MODE must be closed or open, got {fail_mode!r}")
    if mode not in ("enforce", "log_only"):
        raise ValueError(f"MODE must be enforce or log_only, got {mode!r}")
    return Settings(
        guard_model=os.environ.get("GUARD_MODEL", "ru-guard-1.5b-v2"),
        version=os.environ.get("GUARD_VERSION", "0.6.0"),
        ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        ollama_timeout=_float("OLLAMA_TIMEOUT", 30.0),
        ollama_keep_alive=os.environ.get("OLLAMA_KEEP_ALIVE", "30m"),
        api_key=os.environ.get("GUARD_API_KEY", ""),
        audit_salt=os.environ.get("AUDIT_SALT", ""),
        db_path=os.environ.get("DB_PATH", "guard.db"),
        fail_mode=fail_mode,
        mode=mode,
        window_chars=_int("WINDOW_CHARS", 1000),
        overlap_chars=_int("OVERLAP_CHARS", 200),
        max_chars=_int("MAX_CHARS", 12000),
        max_batch_items=_int("MAX_BATCH_ITEMS", 32),
        max_body_bytes=_int("MAX_BODY_BYTES", 2_000_000),
        concurrency=_int("SCAN_CONCURRENCY", 2),
        rate_limit=os.environ.get("RATE_LIMIT", "120/minute"),
        otel_console=os.environ.get("OTEL_CONSOLE", "false").lower() == "true",
        otel_exporter=os.environ.get("OTEL_EXPORTER", "file").strip().lower(),
        otel_file=os.environ.get("OTEL_FILE", os.path.join(os.path.dirname(os.environ.get("DB_PATH", "guard.db")) or ".",
                                                            "traces.jsonl")),
    )
