"""Validate or execute the currently approved Business Listings rollout stage."""

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
    write_json_atomic,
)
from medical_ratings.business_listings_rollout import (
    select_major_metro_probe,
    select_next_paid_rollout_stage,
    validate_large_market_validation_summary,
    validate_rollout_first_page_plan,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)
from medical_ratings.scrape_safety import paid_request_confirmation_text


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or execute one approved Business Listings rollout stage."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--plan", type=Path, default=None)
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--results-directory", type=Path, default=None)
    parser.add_argument("--large-market-summary", type=Path, default=None)
    parser.add_argument("--reference-coverage", type=Path, default=None)
    parser.add_argument("--confirm-submit", default=None)
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "plan": (
                "interim",
                "business_listings_rollout_plan/business_listings_rollout_first_page_plan.csv",
            ),
            "results_directory": ("raw", "business_listings_rollout"),
            "large_market_summary": (
                "interim",
                "business_listings_rollout_market_comparison/"
                "business_listings_rollout_comparison_summary.json",
            ),
            "reference_coverage": (
                "interim",
                "business_listings_rollout_plan/"
                "business_listings_rollout_reference_coverage.csv",
            ),
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
        raise KeyError(f"Rollout result log is missing columns: {sorted(missing)}")
    completed = set(
        log.loc[log["request_status"].eq("completed"), "task_tag"].astype(str)
    )
    continuation_tags = {
        tag
        for tag in completed
        if re.fullmatch(r".+:p\d+", tag)
        and int(tag.rsplit(":p", maxsplit=1)[1]) >= 2
        and f"{tag.rsplit(':p', maxsplit=1)[0]}:p01" in valid_tags
    }
    unexpected = completed - valid_tags - continuation_tags
    if unexpected:
        raise ValueError(f"Rollout result log contains unexpected tags: {sorted(unexpected)}")
    return completed & valid_tags


def safe_raw_name(task_tag: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", task_tag) + ".json"


def main() -> int:
    args = parse_arguments()
    full_plan = validate_rollout_first_page_plan(
        pd.read_csv(args.plan, low_memory=False)
    )
    validation_evidence = None
    standard_rollout_approved = False
    if args.stage == "standard_rollout":
        if not args.large_market_summary.exists():
            raise FileNotFoundError(
                f"Corrected Atlanta comparison is missing: {args.large_market_summary}"
            )
        validation_payload = json.loads(
            args.large_market_summary.read_text(encoding="utf-8")
        )
        if not isinstance(validation_payload, dict):
            raise TypeError("Atlanta comparison summary must contain a JSON object")
        validation_evidence = validate_large_market_validation_summary(
            validation_payload
        )
        standard_rollout_approved = True
    major_metro_reference_envelope = None
    if args.stage == "major_metro_review":
        stage_plan, major_metro_reference_envelope = select_major_metro_probe(
            full_plan,
            pd.read_csv(args.reference_coverage, low_memory=False),
        )
    else:
        stage_plan = select_next_paid_rollout_stage(
            full_plan,
            args.stage,
            standard_rollout_approved=standard_rollout_approved,
        )
    result_log_path = args.results_directory / "business_listings_rollout_result_log.csv"
    raw_directory = args.results_directory / "raw"
    valid_tags = set(full_plan["task_tag"].astype(str))
    stage_tags = set(stage_plan["task_tag"].astype(str))
    finished = completed_tags(result_log_path, valid_tags) & stage_tags
    remaining = stage_plan.loc[~stage_plan["task_tag"].isin(finished)].copy()
    request_kind = (
        "MAJOR_METRO_BUSINESS_LISTINGS"
        if args.stage == "major_metro_review"
        else "BUSINESS_LISTINGS"
    )
    confirmation = paid_request_confirmation_text(request_kind, len(remaining))
    summary = {
        "stage": args.stage,
        "stage_requests": len(stage_plan),
        "stage_markets": sorted(stage_plan["market"].astype(str).unique()),
        "previously_completed_requests": len(finished),
        "remaining_paid_requests": len(remaining),
        "remaining_estimated_minimum_cost_usd": round(
            float(remaining["estimated_minimum_cost_usd"].sum()), 6
        ),
        "remaining_estimated_maximum_cost_usd": round(
            float(remaining["estimated_maximum_cost_usd"].sum()), 6
        ),
        "paid_submission_enabled": args.confirm_submit == confirmation,
        "required_confirmation_text": confirmation,
        "large_market_validation_evidence": validation_evidence,
        "major_metro_reference_envelope": major_metro_reference_envelope,
        "automatic_continuation_requests_submitted": 0,
    }
    if remaining.empty:
        print(json.dumps({**summary, "credentials_read": False, "api_requests_submitted": 0}, indent=2))
        print("Stage is already complete. No API request was submitted.")
        return 0
    if args.confirm_submit != confirmation:
        print(json.dumps({**summary, "credentials_read": False, "api_requests_submitted": 0}, indent=2))
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
    settings = read_settings(args.settings)
    dataforseo = settings.get("dataforseo")
    if not isinstance(dataforseo, dict):
        raise KeyError("settings.yaml is missing dataforseo")
    endpoints = dataforseo.get("endpoints")
    if not isinstance(endpoints, dict) or "business_listings_live" not in endpoints:
        raise KeyError("settings.yaml is missing business_listings_live endpoint")
    endpoint = str(endpoints["business_listings_live"])
    interval = float(dataforseo.get("request_interval_seconds", 1))
    from medical_ratings.config import require_dataforseo_credentials
    from medical_ratings.dataforseo import DataForSEOClient

    login, password = require_dataforseo_credentials()
    client = DataForSEOClient(login, password)

    completed_this_run = 0
    cost_this_run = 0.0
    pages_requiring_continuation: list[str] = []
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
                {
                    **row,
                    **provenance,
                    "raw_file": raw_name,
                    "error_type": None,
                    "error_message": None,
                },
            )
            completed_this_run += 1
            if provenance.get("api_cost_usd") is not None:
                cost_this_run += float(provenance["api_cost_usd"])
            if provenance.get("page_has_more") is True:
                pages_requiring_continuation.append(tag)
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
                "stage": args.stage,
                "credentials_read": True,
                "api_requests_submitted": completed_this_run,
                "api_cost_usd": round(cost_this_run, 6),
                "previously_completed_requests": len(finished),
                "total_completed_requests": len(finished) + completed_this_run,
                "remaining_paid_requests": len(remaining) - completed_this_run,
                "first_pages_requiring_continuation": pages_requiring_continuation,
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
