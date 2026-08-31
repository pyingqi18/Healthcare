"""Configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when required configuration is missing or malformed."""


def load_settings(path: str | Path, *, load_environment: bool = True) -> dict[str, Any]:
    """Load a YAML settings file and validate required top-level sections."""

    if load_environment:
        load_dotenv()

    settings_path = Path(path).expanduser().resolve()
    if not settings_path.exists():
        raise ConfigurationError(f"Settings file not found: {settings_path}")

    with settings_path.open("r", encoding="utf-8") as stream:
        settings = yaml.safe_load(stream) or {}

    required_sections = {"project", "paths", "dataforseo", "study", "model"}
    missing = required_sections.difference(settings)
    if missing:
        raise ConfigurationError(f"Missing settings sections: {sorted(missing)}")

    return settings


def require_dataforseo_credentials() -> tuple[str, str]:
    """Return DataForSEO credentials from environment variables."""

    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        raise ConfigurationError(
            "DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD must be set in the environment"
        )
    return login, password
