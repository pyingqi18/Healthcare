"""Plan or execute audited Business Listings continuation pages."""

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
    build_rollout_continuation_plan,
    validate_rollout_first_page_plan,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)
from medical_ratings.scrape_safety import paid_request_confirmation_text


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan or execute audited Business Listings continuation pages."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--first-page-plan", type=Path, default=None)
    parser.add_argument("--page-completeness", type=Path, default=None)
    parser.add_argument("--plan-config", type=Path, default=Path("config/scrape_plans.yaml"))
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--results-directory", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--confirm-submit", default=None)
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "first_page_plan": (
                "interim",
                "business_listings_rollout_plan/business_listings_rollout_first_page_plan.csv",
            ),
            "page_completeness": (
                "interim",
                "business_listings_rollout_pagination_audit/business_listings_page_completeness.csv",
            ),
            "results_directory": ("raw", "business_listings_rollout"),
            "output_directory": ("interim", "business_listings_rollout_continuations"),
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
    if path.exists():
        old = pd.read_csv(path, low_memory=False)
        columns = list(dict.fromkeys([*old.columns, *new.columns]))
        output = pd.concat([old, new], ignore_index=True).reindex(columns=columns)
    else:
        output = new
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    output.to_csv(temporary, index=False)
    temporary.replace(path)


def safe_raw_name(task_tag: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", task_tag) + ".json"


def main() -> int:
    args = parse_arguments()
    plan_config = read_yaml(args.plan_config)
    pricing = plan_config.get("pricing")
    if not isinstance(pricing, dict):
        raise KeyError("scrape_plans.yaml is missing pricing")
    first_page_plan = validate_rollout_first_page_plan(
        pd.read_csv(args.first_page_plan, low_memory=False)
    )
    continuation, plan_summary = build_rollout_continuation_plan(
        first_page_plan,
        pd.read_csv(args.page_completeness, low_memory=False),
        request_cost_usd=float(pricing["business_listings_live_per_request"]),
        item_cost_usd=float(pricing["business_listings_live_per_item"]),
    )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    continuation_path = args.output_directory / "business_listings_rollout_continuation_plan.csv"
    summary_path = args.output_directory / "business_listings_rollout_continuation_summary.json"
    continuation.to_csv(continuation_path, index=False)
    summary_path.write_text(
        json.dumps(plan_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    result_log_path = args.results_directory / "business_listings_rollout_result_log.csv"
    raw_directory = args.results_directory / "raw"
    completed: set[str] = set()
    if result_log_path.exists():
        result_log = pd.read_csv(result_log_path, low_memory=False)
        required = {"task_tag", "request_status"}
        missing = required - set(result_log.columns)
        if missing:
            raise KeyError(f"Rollout result log is missing columns: {sorted(missing)}")
        completed = set(
            result_log.loc[
                result_log["request_status"].eq("completed"), "task_tag"
            ].astype(str)
        ) & set(continuation["task_tag"].astype(str))
    remaining = continuation.loc[~continuation["task_tag"].isin(completed)].copy()
    confirmation = paid_request_confirmation_text("BUSINESS_LISTINGS", len(remaining))
    execution_summary = {
        **plan_summary,
        "previously_completed_continuation_requests": len(completed),
        "remaining_paid_requests": len(remaining),
        "paid_submission_enabled": args.confirm_submit == confirmation,
        "required_confirmation_text": confirmation,
        "continuation_plan": str(continuation_path),
    }
    if remaining.empty:
        print(json.dumps({**execution_summary, "credentials_read": False, "api_requests_submitted": 0}, indent=2))
        print("Continuation plan is already complete. No API request was submitted.")
        return 0
    if args.confirm_submit != confirmation:
        print(json.dumps({**execution_summary, "credentials_read": False, "api_requests_submitted": 0}, indent=2))
        print("Validation only. No credentials were read and no API request was submitted.")
        return 0

    settings = read_yaml(args.settings)
    dataforseo = settings.get("dataforseo")
    if not isinstance(dataforseo, dict):
        raise KeyError("settings.yaml is missing dataforseo")
    endpoints = dataforseo.get("endpoints")
    if not isinstance(endpoints, dict) or "business_listings_live" not in endpoints:
        raise KeyError("settings.yaml is missing business_listings_live endpoint")
    from medical_ratings.config import require_dataforseo_credentials
    from medical_ratings.dataforseo import DataForSEOClient

    login, password = require_dataforseo_credentials()
    client = DataForSEOClient(login, password)
    endpoint = str(endpoints["business_listings_live"])
    interval = float(dataforseo.get("request_interval_seconds", 1))
    submitted = 0
    cost = 0.0
    total_count_drift: list[str] = []
    pages_still_reporting_more: list[str] = []
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
                offset=int(row["offset"]),
            )
            write_json_atomic(payload, raw_path)
            observed_total = provenance.get("total_count")
            drift = (
                observed_total is not None
                and int(observed_total) != int(row["audited_total_count"])
            )
            append_log_atomic(
                result_log_path,
                {
                    **row,
                    **provenance,
                    "raw_file": raw_name,
                    "total_count_drift": drift,
                    "error_type": None,
                    "error_message": None,
                },
            )
            submitted += 1
            if provenance.get("api_cost_usd") is not None:
                cost += float(provenance["api_cost_usd"])
            if drift:
                total_count_drift.append(tag)
            if provenance.get("page_has_more") is True:
                pages_still_reporting_more.append(tag)
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
                "api_requests_submitted": submitted,
                "api_cost_usd": round(cost, 6),
                "previously_completed_continuation_requests": len(completed),
                "total_completed_continuation_requests": len(completed) + submitted,
                "remaining_paid_requests": len(remaining) - submitted,
                "total_count_drift_task_tags": total_count_drift,
                "pages_still_reporting_more": pages_still_reporting_more,
                "automatic_unplanned_requests_submitted": 0,
                "result_log": str(result_log_path),
                "raw_directory": str(raw_directory),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
