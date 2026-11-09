"""Service configuration read from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """guard-api settings."""

    guard_model: str
    version: str


def get_settings() -> Settings:
    """Build settings from the environment."""
    return Settings(
        guard_model=os.environ.get("GUARD_MODEL", "ru-guard-0.5b"),
        version=os.environ.get("GUARD_VERSION", "0.0.0"),
    )
