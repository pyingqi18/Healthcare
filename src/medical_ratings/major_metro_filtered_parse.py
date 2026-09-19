"""Offline completeness audit and parsing for ZIP-filtered major metros."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.business_listings_live import (
    deduplicate_business_listings,
    parse_business_listings_payload,
)
from medical_ratings.business_listings_rollout import (
    audit_major_metro_filtered_page_log,
)


def _zip_pattern(filters_json: object) -> re.Pattern[str]:
    filters = json.loads(str(filters_json))
    if (
        not isinstance(filters, list)
        or len(filters) != 1
        or not isinstance(filters[0], list)
        or len(filters[0]) != 3
        or filters[0][0] != "address_info.zip"
        or filters[0][1] != "regex"
    ):
        raise ValueError("Expected one address_info.zip regex filter")
    return re.compile(str(filters[0][2]))


def _latest_completed_pages(page_log: pd.DataFrame) -> pd.DataFrame:
    required = {
        "page_request_tag",
        "group_id",
        "market",
        "category_group",
        "page_number",
        "api_task_tag",
        "request_status",
        "raw_file",
        "retrieved_at_utc",
        "item_count",
    }
    missing = required - set(page_log.columns)
    if missing:
        raise KeyError(f"Filtered page log is missing columns: {sorted(missing)}")
    latest = page_log.drop_duplicates("page_request_tag", keep="last").copy()
    completed = latest.loc[latest["request_status"].eq("completed")].copy()
    if completed["page_request_tag"].astype(str).duplicated().any():
        raise ValueError("Filtered page log contains duplicate completed page tags")
    return completed


def audit_and_parse_major_metro_filtered_pages(
    page_log: pd.DataFrame,
    group_plan: pd.DataFrame,
    raw_directory: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Require four complete token chains, parse raw pages, and deduplicate profiles."""

    expected_groups = {
        "LA_CA_L:g01",
        "LA_CA_L:g02",
        "NYC_NY_L:g01",
        "NYC_NY_L:g02",
    }
    if set(group_plan["group_id"].astype(str)) != expected_groups:
        raise ValueError("Major-metro parse requires exactly four LA and NYC groups")
    state, state_summary = audit_major_metro_filtered_page_log(page_log, group_plan)
    if (
        int(state_summary["completed_groups"]) != 4
        or int(state_summary["remaining_planned_requests"]) != 0
    ):
        raise ValueError("ZIP-filtered major-metro token chains are incomplete")
    completed = _latest_completed_pages(page_log)
    if len(completed) != int(state_summary["completed_page_requests"]):
        raise ValueError("Completed page log differs from the audited token-chain state")

    plan_by_group = group_plan.set_index(group_plan["group_id"].astype(str))
    records: list[dict[str, Any]] = []
    for row in completed.sort_values(
        ["market", "category_group", "page_number"]
    ).to_dict(orient="records"):
        group_id = str(row["group_id"])
        source = plan_by_group.loc[group_id]
        expected_api_tag = str(source["api_task_tag"])
        if str(row["api_task_tag"]) != expected_api_tag:
            raise ValueError(f"{row['page_request_tag']} has an unexpected API tag")
        raw_path = Path(raw_directory) / str(row["raw_file"])
        if not raw_path.is_file():
            raise FileNotFoundError(f"Missing ZIP-filtered raw response: {raw_path}")
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        parsed = parse_business_listings_payload(
            payload,
            expected_tag=expected_api_tag,
            market=str(row["market"]),
            retrieved_at_utc=str(row["retrieved_at_utc"]),
        )
        if len(parsed) != int(row["item_count"]):
            raise ValueError(
                f"{row['page_request_tag']} parsed count differs from the result log"
            )
        pattern = _zip_pattern(source["filters_json"])
        for record in parsed:
            zip_value = record.get("zip")
            if zip_value is None or pattern.fullmatch(str(zip_value).strip()) is None:
                raise ValueError(
                    f"{row['page_request_tag']} contains a result outside its ZIP filter"
                )
            record["api_task_tag"] = expected_api_tag
            record["task_tag"] = str(row["page_request_tag"])
            record["page_number"] = int(row["page_number"])
            record["category_group"] = int(row["category_group"])
            record["group_id"] = group_id
            records.append(record)
    if len(records) != int(state_summary["saved_items"]):
        raise ValueError("Parsed observations differ from audited saved item counts")
    observations = pd.DataFrame.from_records(records)

    candidates_by_market: list[pd.DataFrame] = []
    market_records: list[dict[str, Any]] = []
    for market, market_observations in observations.groupby(
        "requested_location", sort=True
    ):
        for group_id, group_observations in market_observations.groupby(
            "group_id", sort=True
        ):
            group_unique = deduplicate_business_listings(group_observations)
            if len(group_unique) != len(group_observations):
                raise ValueError(
                    f"{group_id} repeats a stable profile within its token chain"
                )
        candidates = deduplicate_business_listings(market_observations)
        candidates_by_market.append(candidates)
        market_records.append(
            {
                "market": str(market),
                "category_groups": int(market_observations["category_group"].nunique()),
                "completed_pages": int(market_observations["task_tag"].nunique()),
                "parsed_observations": len(market_observations),
                "unique_profile_candidates": len(candidates),
                "cross_category_duplicate_observations_removed": (
                    len(market_observations) - len(candidates)
                ),
            }
        )
    candidates = pd.concat(candidates_by_market, ignore_index=True)
    market_summary = pd.DataFrame.from_records(market_records)
    summary = {
        "analysis_status": "major_metro_zip_filtered_pagination_audited_and_parsed",
        "api_requests_submitted": 0,
        "markets_parsed": int(market_summary["market"].nunique()),
        "category_groups_parsed": int(state_summary["category_groups"]),
        "completed_pages_parsed": int(state_summary["completed_page_requests"]),
        "parsed_observations": len(observations),
        "unique_profile_candidates_within_markets": len(candidates),
        "cross_category_duplicate_observations_removed": len(observations) - len(candidates),
        "all_results_match_server_zip_filter": True,
        "total_count_drift_groups": state_summary["total_count_drift_groups"],
        "automatic_profile_or_location_merges": 0,
        "interpretation_limit": (
            "Profiles are deduplicated only by stable Google identity within each market; "
            "physical competition locations are not yet resolved."
        ),
    }
    return (
        observations.reset_index(drop=True),
        candidates.reset_index(drop=True),
        state.reset_index(drop=True),
        market_summary.reset_index(drop=True),
        summary,
    )
