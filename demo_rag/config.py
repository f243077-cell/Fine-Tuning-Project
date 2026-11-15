"""demo_rag settings from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

PKG = Path(__file__).resolve().parent


def _bool(name: str, default: bool) -> bool:
    """Boolean environment variable (true/false, 1/0)."""
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    """Reference RAG settings (Architecture.md section 12)."""

    guard_url: str = "http://localhost:8001"
    guard_api_key: str = ""
    guard_enabled: bool = True
    allow_guard_toggle: bool = False
    ollama_url: str = "http://localhost:11434"
    chat_model: str = "qwen2.5:1.5b-instruct"
    chat_timeout: float = 180.0
    chroma_path: str = str(PKG / "chroma")
    collection: str = "noorbagh"
    corpus_dir: str = str(PKG / "corpus")
    poisoned_dir: str = str(PKG / "corpus_poisoned")
    top_k: int = 4
    context_tokens: int = 1500
    recursion_limit: int = 12


def get_settings() -> Settings:
    """Build settings from the environment."""
    d = Settings()
    return Settings(
        guard_url=os.environ.get("GUARD_URL", d.guard_url),
        guard_api_key=os.environ.get("GUARD_API_KEY", ""),
        guard_enabled=_bool("GUARD_ENABLED", True),
        allow_guard_toggle=_bool("ALLOW_GUARD_TOGGLE", False),
        ollama_url=os.environ.get("OLLAMA_URL", d.ollama_url).rstrip("/"),
        chat_model=os.environ.get("CHAT_MODEL", d.chat_model),
        chat_timeout=float(os.environ.get("CHAT_TIMEOUT", d.chat_timeout)),
        chroma_path=os.environ.get("CHROMA_PATH", d.chroma_path),
        collection=os.environ.get("CHROMA_COLLECTION", d.collection),
        corpus_dir=os.environ.get("CORPUS_DIR", d.corpus_dir),
        poisoned_dir=os.environ.get("POISONED_DIR", d.poisoned_dir),
        top_k=int(os.environ.get("TOP_K", d.top_k)),
        context_tokens=int(os.environ.get("CONTEXT_TOKENS", d.context_tokens)),
        recursion_limit=int(os.environ.get("RECURSION_LIMIT", d.recursion_limit)),
    )
