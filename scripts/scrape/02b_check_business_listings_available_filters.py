"""Inspect Business Listings filter fields without submitting a paid task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from medical_ratings.config import require_dataforseo_credentials
from medical_ratings.dataforseo import DataForSEOClient
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether Business Listings exposes ZIP/postal filters."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "output": (
                "interim",
                "business_listings_major_metro_scope_audit/"
                "business_listings_available_filters.json",
            )
        },
    )


def read_yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return value


def matching_paths(value: Any, *, path: str = "root") -> list[str]:
    """Return compact JSON paths containing ZIP, postal, or address evidence."""

    terms = ("zip", "postal", "address_info")
    matches: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            next_path = f"{path}.{key}"
            if any(term in str(key).lower() for term in terms):
                matches.append(next_path)
            matches.extend(matching_paths(nested, path=next_path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            matches.extend(matching_paths(nested, path=f"{path}[{index}]"))
    elif isinstance(value, str) and any(term in value.lower() for term in terms):
        matches.append(f"{path}={value}")
    return sorted(set(matches))


def main() -> int:
    args = parse_arguments()
    settings = read_yaml(args.settings)
    dataforseo = settings.get("dataforseo")
    if not isinstance(dataforseo, dict):
        raise KeyError("settings.yaml is missing dataforseo")
    endpoints = dataforseo.get("endpoints")
    if not isinstance(endpoints, dict):
        raise KeyError("settings.yaml is missing DataForSEO endpoints")
    endpoint = str(endpoints.get("business_listings_available_filters", ""))
    login, password = require_dataforseo_credentials()
    payload = DataForSEOClient(login, password).get_business_listings_available_filters(
        endpoint
    )
    paths = matching_paths(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(args.output)
    summary = {
        "analysis_status": "business_listings_available_filters_checked",
        "credentials_read": True,
        "paid_api_requests_submitted": 0,
        "available_filter_get_requests": 1,
        "zip_or_postal_filter_evidence_found": bool(paths),
        "matching_filter_paths": paths,
        "saved_response": str(args.output),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
