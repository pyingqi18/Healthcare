"""Validate or run four ZIP-filtered major-metro count probes."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.business_listings_live import parse_category_cell, write_json_atomic
from medical_ratings.business_listings_rollout import (
    build_major_metro_filtered_count_plan,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)
from medical_ratings.scrape_safety import paid_request_confirmation_text


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or run four limit-one ZIP-filtered count probes."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--plan", type=Path, default=None)
    parser.add_argument("--plan-config", type=Path, default=Path("config/scrape_plans.yaml"))
    parser.add_argument("--regions", type=Path, default=Path("config/regions.yaml"))
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--results-directory", type=Path, default=None)
    parser.add_argument("--confirm-submit", default=None)
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "plan": (
                "interim",
                "business_listings_rollout_plan/business_listings_rollout_first_page_plan.csv",
            ),
            "results_directory": (
                "raw",
                "business_listings_major_metro_filter_count",
            ),
        },
    )


def read_yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return value


def append_log_atomic(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = pd.DataFrame([record])
    old = pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
    columns = list(dict.fromkeys([*old.columns, *new.columns]))
    output = pd.concat([old, new], ignore_index=True).reindex(columns=columns)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    output.to_csv(temporary, index=False)
    temporary.replace(path)


def safe_raw_name(task_tag: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", task_tag) + ".json"


def completed_tags(path: Path, valid_tags: set[str]) -> set[str]:
    if not path.exists():
        return set()
    log = pd.read_csv(path, low_memory=False)
    required = {"task_tag", "request_status"}
    missing = required - set(log.columns)
    if missing:
        raise KeyError(f"Filtered count log is missing columns: {sorted(missing)}")
    completed = set(
        log.loc[log["request_status"].eq("completed"), "task_tag"].astype(str)
    )
    unexpected = completed - valid_tags
    if unexpected:
        raise ValueError(f"Filtered count log contains unexpected tags: {sorted(unexpected)}")
    return completed


def completed_count_summary(path: Path, valid_tags: set[str]) -> list[dict[str, object]]:
    if not path.exists():
        return []
    log = pd.read_csv(path, low_memory=False)
    completed = log.loc[
        log["request_status"].eq("completed")
        & log["task_tag"].astype(str).isin(valid_tags)
    ].copy()
    if len(completed) != len(valid_tags):
        return []
    return [
        {
            "market": str(row.market),
            "category_group": int(row.category_group),
            "filtered_total_count": int(row.total_count),
            "returned_items": int(row.item_count),
            "api_cost_usd": float(row.api_cost_usd),
        }
        for row in completed.sort_values(["market", "category_group"]).itertuples()
    ]


def main() -> int:
    args = parse_arguments()
    plan_config = read_yaml(args.plan_config)
    count_plan, plan_summary = build_major_metro_filtered_count_plan(
        pd.read_csv(args.plan, low_memory=False),
        plan_config,
        read_yaml(args.regions),
    )
    result_log_path = args.results_directory / "major_metro_filter_count_result_log.csv"
    raw_directory = args.results_directory / "raw"
    valid_tags = set(count_plan["task_tag"].astype(str))
    finished = completed_tags(result_log_path, valid_tags)
    remaining = count_plan.loc[~count_plan["task_tag"].isin(finished)].copy()
    confirmation = paid_request_confirmation_text(
        "MAJOR_METRO_FILTER_COUNT", len(remaining)
    )
    summary = {
        **plan_summary,
        "previously_completed_requests": len(finished),
        "remaining_paid_requests": len(remaining),
        "remaining_estimated_cost_usd": round(
            float(remaining["estimated_cost_usd"].sum()), 6
        ),
        "paid_submission_enabled": args.confirm_submit == confirmation,
        "required_confirmation_text": confirmation,
    }
    if remaining.empty:
        print(
            json.dumps(
                {
                    **summary,
                    "filtered_counts": completed_count_summary(
                        result_log_path, valid_tags
                    ),
                    "credentials_read": False,
                    "api_requests_submitted": 0,
                },
                indent=2,
            )
        )
        return 0
    if args.confirm_submit != confirmation:
        print(
            json.dumps(
                {**summary, "credentials_read": False, "api_requests_submitted": 0},
                indent=2,
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
        )
    )
    settings = read_yaml(args.settings)
    dataforseo = settings.get("dataforseo")
    if not isinstance(dataforseo, dict):
        raise KeyError("settings.yaml is missing dataforseo")
    endpoints = dataforseo.get("endpoints")
    if not isinstance(endpoints, dict):
        raise KeyError("settings.yaml is missing DataForSEO endpoints")
    endpoint = str(endpoints["business_listings_live"])
    interval = float(dataforseo.get("request_interval_seconds", 1))
    from medical_ratings.config import require_dataforseo_credentials
    from medical_ratings.dataforseo import DataForSEOClient

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
                f"Raw response exists without completed log row for {tag}; refusing resubmission"
            )
        try:
            payload, provenance = client.search_business_listings_live(
                url=endpoint,
                categories=parse_category_cell(row["categories"]),
                location_coordinate=str(row["location_coordinate"]),
                limit=1,
                tag=tag,
                filters=json.loads(str(row["filters_json"])),
            )
            write_json_atomic(payload, raw_path)
            append_log_atomic(
                result_log_path,
                {
                    **row,
                    **provenance,
                    "raw_file": raw_name,
                    "error_type": None,
                    "error_message": None,
                },
            )
            completed_this_run += 1
            cost_this_run += float(provenance.get("api_cost_usd") or 0.0)
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
                "total_completed_requests": len(finished) + completed_this_run,
                "remaining_paid_requests": len(remaining) - completed_this_run,
                "filtered_counts": completed_count_summary(result_log_path, valid_tags),
                "automatic_continuation_requests_submitted": 0,
                "result_log": str(result_log_path),
                "raw_directory": str(raw_directory),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
