"""Validate or run ZIP-filtered major-metro Business Listings token chains."""

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
    audit_major_metro_filtered_page_log,
    build_major_metro_filtered_page_plan,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)
from medical_ratings.scrape_safety import paid_request_confirmation_text


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or run the four ZIP-filtered major-metro token chains."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--plan", type=Path, default=None)
    parser.add_argument("--count-log", type=Path, default=None)
    parser.add_argument("--plan-config", type=Path, default=Path("config/scrape_plans.yaml"))
    parser.add_argument("--regions", type=Path, default=Path("config/regions.yaml"))
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--results-directory", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--confirm-submit", default=None)
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "plan": (
                "interim",
                "business_listings_rollout_plan/business_listings_rollout_first_page_plan.csv",
            ),
            "count_log": (
                "raw",
                "business_listings_major_metro_filter_count/major_metro_filter_count_result_log.csv",
            ),
            "results_directory": (
                "raw",
                "business_listings_major_metro_zip_filtered",
            ),
            "output_directory": (
                "interim",
                "business_listings_major_metro_zip_filtered",
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


def safe_raw_name(page_request_tag: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", page_request_tag) + ".json"


def read_page_log(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def state_for_group(state: pd.DataFrame, group_id: str) -> dict[str, object]:
    selected = state.loc[state["group_id"].astype(str).eq(group_id)]
    if len(selected) != 1:
        raise ValueError(f"Expected exactly one state row for {group_id}")
    return selected.iloc[0].to_dict()


def main() -> int:
    args = parse_arguments()
    plan_config = read_yaml(args.plan_config)
    group_plan, plan_summary = build_major_metro_filtered_page_plan(
        pd.read_csv(args.plan, low_memory=False),
        pd.read_csv(args.count_log, low_memory=False),
        plan_config,
        read_yaml(args.regions),
    )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    plan_path = args.output_directory / "major_metro_zip_filtered_page_plan.csv"
    plan_summary_path = args.output_directory / "major_metro_zip_filtered_page_plan.json"
    group_plan.to_csv(plan_path, index=False)
    plan_summary_path.write_text(
        json.dumps(plan_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    result_log_path = args.results_directory / "major_metro_zip_filtered_page_log.csv"
    raw_directory = args.results_directory / "raw"
    page_log = read_page_log(result_log_path)
    state, state_summary = audit_major_metro_filtered_page_log(page_log, group_plan)
    remaining = int(state_summary["remaining_planned_requests"])
    confirmation = paid_request_confirmation_text(
        "MAJOR_METRO_ZIP_FILTERED_PAGE", remaining
    )
    pricing = plan_config.get("pricing")
    if not isinstance(pricing, dict):
        raise KeyError("scrape_plans.yaml is missing pricing")
    request_cost = float(pricing["business_listings_live_per_request"])
    item_cost = float(pricing["business_listings_live_per_item"])
    remaining_items = int(
        (
            state["latest_total_count"].astype(int)
            - state["saved_items"].astype(int)
        ).clip(lower=0).sum()
    )
    validation = {
        **plan_summary,
        **state_summary,
        "remaining_estimated_cost_usd": round(
            remaining * request_cost + remaining_items * item_cost, 6
        ),
        "paid_submission_enabled": args.confirm_submit == confirmation,
        "required_confirmation_text": confirmation,
        "credentials_read": False,
        "api_requests_submitted": 0,
        "page_plan": str(plan_path),
        "result_log": str(result_log_path),
    }
    if remaining == 0:
        print(json.dumps(validation, indent=2))
        print("ZIP-filtered major-metro pagination is already complete.")
        return 0
    if args.confirm_submit != confirmation:
        print(json.dumps(validation, indent=2))
        print("Validation only. No credentials were read and no API request was submitted.")
        return 0

    print(
        json.dumps(
            {
                **validation,
                "execution_authorized": True,
                "requests_about_to_submit_at_most": remaining,
            },
            indent=2,
        )
    )
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
    drift_groups: set[str] = set()
    authorization_cap_reached = False

    for group in group_plan.sort_values(["market", "category_group"]).to_dict(
        orient="records"
    ):
        group_id = str(group["group_id"])
        current_state = state_for_group(state, group_id)
        while not bool(current_state["group_complete"]):
            if submitted >= remaining:
                authorization_cap_reached = True
                break
            page_number = int(current_state["completed_pages"]) + 1
            page_request_tag = f"{group['api_task_tag']}:p{page_number:02d}"
            raw_name = safe_raw_name(page_request_tag)
            raw_path = raw_directory / raw_name
            if raw_path.exists():
                raise RuntimeError(
                    "A raw response exists without a completed page-log row for "
                    f"{page_request_tag}; refusing a potentially duplicate paid request"
                )
            offset_token = current_state["next_offset_token"]
            if page_number == 1:
                offset_token = None
            elif offset_token is None or not str(offset_token).strip():
                raise RuntimeError(f"{group_id} is incomplete but has no continuation token")
            try:
                payload, provenance = client.search_business_listings_live(
                    url=endpoint,
                    categories=parse_category_cell(group["categories"]),
                    location_coordinate=str(group["location_coordinate"]),
                    limit=int(group["limit"]),
                    tag=str(group["api_task_tag"]),
                    offset_token=None if offset_token is None else str(offset_token),
                    filters=json.loads(str(group["filters_json"])),
                )
                write_json_atomic(payload, raw_path)
                api_task_tag = provenance.pop("task_tag")
                observed_total = int(provenance["total_count"])
                drift = observed_total != int(group["audited_total_count"])
                append_log_atomic(
                    result_log_path,
                    {
                        "page_request_tag": page_request_tag,
                        "group_id": group_id,
                        "market": group["market"],
                        "category_group": int(group["category_group"]),
                        "page_number": page_number,
                        "api_task_tag": api_task_tag,
                        "audited_total_count": int(group["audited_total_count"]),
                        **provenance,
                        "raw_file": raw_name,
                        "total_count_drift": drift,
                        "error_type": None,
                        "error_message": None,
                    },
                )
                submitted += 1
                cost += float(provenance.get("api_cost_usd") or 0.0)
                if drift:
                    drift_groups.add(group_id)
            except Exception as error:
                append_log_atomic(
                    result_log_path,
                    {
                        "page_request_tag": page_request_tag,
                        "group_id": group_id,
                        "market": group["market"],
                        "category_group": int(group["category_group"]),
                        "page_number": page_number,
                        "api_task_tag": group["api_task_tag"],
                        "request_status": "failed",
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                    },
                )
                raise
            time.sleep(interval)
            page_log = read_page_log(result_log_path)
            state, state_summary = audit_major_metro_filtered_page_log(
                page_log, group_plan
            )
            current_state = state_for_group(state, group_id)
        if authorization_cap_reached:
            break

    final_log = read_page_log(result_log_path)
    final_state, final_summary = audit_major_metro_filtered_page_log(
        final_log, group_plan
    )
    state_path = args.output_directory / "major_metro_zip_filtered_page_state.csv"
    summary_path = args.output_directory / "major_metro_zip_filtered_page_summary.json"
    final_state.to_csv(state_path, index=False)
    final_output = {
        "execution_completed": final_summary["remaining_planned_requests"] == 0,
        "credentials_read": True,
        "api_requests_submitted": submitted,
        "api_cost_usd": round(cost, 6),
        **final_summary,
        "total_count_drift_groups": sorted(
            set(final_summary["total_count_drift_groups"]) | drift_groups
        ),
        "authorization_cap_reached": authorization_cap_reached,
        "automatic_unplanned_requests_submitted": 0,
        "result_log": str(result_log_path),
        "raw_directory": str(raw_directory),
        "state_file": str(state_path),
    }
    summary_path.write_text(
        json.dumps(final_output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(final_output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
