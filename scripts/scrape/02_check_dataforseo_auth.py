"""Check DataForSEO API credentials without exposing account secrets."""

from __future__ import annotations

from typing import Any

from medical_ratings.config import require_dataforseo_credentials
from medical_ratings.dataforseo import DataForSEOClient


def check_authentication(
    login: str,
    password: str,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Call the free User Data endpoint through the shared client."""

    client = DataForSEOClient(login, password, timeout=timeout)
    return client.check_authentication()


def main() -> int:
    login, password = require_dataforseo_credentials()

    summary = check_authentication(login, password)
    print("API status:", summary["api_status"])
    print("Authenticated:", summary["authenticated"])
    return 0 if summary["authenticated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
