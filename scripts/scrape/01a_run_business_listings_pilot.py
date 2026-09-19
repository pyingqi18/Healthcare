"""Validate or execute the four-request live Business Listings pilot."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.business_listings_live import (
    parse_category_cell,
    validate_pilot_manifest,
    write_json_atomic,
)
from medical_ratings.config import require_dataforseo_credentials
from medical_ratings.dataforseo import DataForSEOClient
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)
from medical_ratings.scrape_safety import paid_request_confirmation_text


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or run the four-request Business Listings pilot."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--results-directory", type=Path, default=None)
    parser.add_argument("--confirm-submit", default=None)
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "manifest": ("interim", "business_listings_pilot_plan/business_listings_pilot_manifest.csv"),
            "results_directory": ("raw", "business_listings_pilot"),
        },
    )


def read_settings(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return payload


def append_log_atomic(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = pd.DataFrame([record])
    if path.exists():
        old = pd.read_csv(path, low_memory=False)
        columns = list(dict.fromkeys([*old.columns, *new.columns]))
        output = pd.concat([old, new], ignore_index=True).reindex(columns=columns)
    else:
        output = new
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    output.to_csv(temporary, index=False)
    temporary.replace(path)


def completed_tags(path: Path, valid_tags: set[str]) -> set[str]:
    if not path.exists():
        return set()
    log = pd.read_csv(path, low_memory=False)
    required = {"task_tag", "request_status"}
    missing = required - set(log.columns)
    if missing:
        raise KeyError(f"Pilot result log is missing columns: {sorted(missing)}")
    completed = set(
        log.loc[log["request_status"].eq("completed"), "task_tag"].astype(str)
    )
    unexpected = completed - valid_tags
    if unexpected:
        raise ValueError(f"Pilot result log contains unexpected tags: {sorted(unexpected)}")
    return completed


def safe_raw_name(task_tag: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", task_tag) + ".json"


def main() -> int:
    args = parse_arguments()
    manifest = validate_pilot_manifest(pd.read_csv(args.manifest, low_memory=False))
    result_log_path = args.results_directory / "business_listings_result_log.csv"
    raw_directory = args.results_directory / "raw"
    valid_tags = set(manifest["task_tag"].astype(str))
    finished = completed_tags(result_log_path, valid_tags)
    remaining = manifest.loc[~manifest["task_tag"].isin(finished)].copy()
    confirmation = paid_request_confirmation_text(
        "BUSINESS_LISTINGS", len(remaining)
    )
    summary = {
        "manifest_requests": len(manifest),
        "previously_completed_requests": len(finished),
        "remaining_paid_requests": len(remaining),
        "paid_submission_enabled": args.confirm_submit == confirmation,
        "required_confirmation_text": confirmation,
    }
    if remaining.empty:
        print(
            json.dumps(
                {
                    **summary,
                    "credentials_read": False,
                    "api_requests_submitted": 0,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        print("Pilot is already complete. No API request was submitted.")
        return 0
    if args.confirm_submit != confirmation:
        print(
            json.dumps(
                {
                    **summary,
                    "credentials_read": False,
                    "api_requests_submitted": 0,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        print("Validation only. No credentials were read and no API request was submitted.")
        return 0

    print(
        json.dumps(
            {
                **summary,
                "execution_authorized": True,
                "requests_about_to_submit": len(remaining),
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    settings = read_settings(args.settings)
    dataforseo = settings.get("dataforseo")
    if not isinstance(dataforseo, dict):
        raise KeyError("settings.yaml is missing dataforseo")
    endpoints = dataforseo.get("endpoints")
    if not isinstance(endpoints, dict) or "business_listings_live" not in endpoints:
        raise KeyError("settings.yaml is missing business_listings_live endpoint")
    endpoint = str(endpoints["business_listings_live"])
    interval = float(dataforseo.get("request_interval_seconds", 1))
    login, password = require_dataforseo_credentials()
    client = DataForSEOClient(login, password)

    completed_this_run = 0
    cost_this_run = 0.0
    for row in remaining.to_dict(orient="records"):
        tag = str(row["task_tag"])
        raw_name = safe_raw_name(tag)
        raw_path = raw_directory / raw_name
        if raw_path.exists():
            raise RuntimeError(
                "A raw response exists without a completed result-log row for "
                f"{tag}. Refusing to resubmit a potentially charged request."
            )
        try:
            payload, provenance = client.search_business_listings_live(
                url=endpoint,
                categories=parse_category_cell(row["categories"]),
                location_coordinate=str(row["location_coordinate"]),
                limit=int(row["limit"]),
                tag=tag,
            )
            write_json_atomic(payload, raw_path)
            append_log_atomic(
                result_log_path,
                {**row, **provenance, "raw_file": raw_name, "error_type": None, "error_message": None},
            )
            completed_this_run += 1
            if provenance.get("api_cost_usd") is not None:
                cost_this_run += float(provenance["api_cost_usd"])
        except Exception as error:
            append_log_atomic(
                result_log_path,
                {
                    **row,
                    "request_status": "failed",
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
            )
            raise
        time.sleep(interval)
    print(
        json.dumps(
            {
                "execution_completed": True,
                "credentials_read": True,
                "api_requests_submitted": completed_this_run,
                "api_cost_usd": round(cost_this_run, 6),
                "previously_completed_requests": len(finished),
                "total_completed_requests": len(finished) + completed_this_run,
                "remaining_paid_requests": len(remaining) - completed_this_run,
                "result_log": str(result_log_path),
                "raw_directory": str(raw_directory),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
