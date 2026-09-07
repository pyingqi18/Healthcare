"""Check DataForSEO API credentials without exposing account secrets."""

from __future__ import annotations

import os
from typing import Any

import requests


USER_DATA_URL = "https://api.dataforseo.com/v3/appendix/user_data"


def check_authentication(
    login: str,
    password: str,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Call the free User Data endpoint and return a safe summary."""

    response = requests.get(
        USER_DATA_URL,
        auth=(login.strip(), password.strip()),
        timeout=timeout,
    )

    summary: dict[str, Any] = {
        "http_status": response.status_code,
        "api_status": None,
        "authenticated": False,
    }
    if response.status_code == 200:
        payload = response.json()
        summary["api_status"] = payload.get("status_code")
        summary["authenticated"] = payload.get("status_code") == 20000

    return summary


def main() -> int:
    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not login or not password:
        raise RuntimeError(
            "Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD first"
        )

    summary = check_authentication(login, password)
    print("HTTP status:", summary["http_status"])
    if summary["api_status"] is not None:
        print("API status:", summary["api_status"])
    print("Authenticated:", summary["authenticated"])
    return 0 if summary["authenticated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
