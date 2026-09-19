"""Plan the staged Business Listings rollout without submitting paid requests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from math import asin, ceil, cos, radians, sin, sqrt
import re
from typing import Any

import pandas as pd

from medical_ratings.business_listings_live import (
    audit_business_listings_page_groups,
    parse_category_cell,
)
from medical_ratings.business_listings_pilot import validate_official_categories
from medical_ratings.identifiers import normalize_zip


EARTH_RADIUS_KM = 6371.0088


REQUIRED_ROLLOUT_PLAN_COLUMNS = {
    "task_tag",
    "stage",
    "execution_status",
    "market",
    "category_group",
    "categories",
    "category_count",
    "location_coordinate",
    "radius_km",
    "limit",
    "page_number",
    "planning_only",
    "execution_enabled",
}


def validate_large_market_validation_summary(
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the corrected Atlanta comparison before standard rollout."""

    if summary.get("analysis_status") != (
        "rollout_market_comparison_before_manual_location_resolution"
    ):
        raise ValueError("Atlanta validation summary has an unexpected analysis status")
    if summary.get("market") != "Atlanta_GA_L":
        raise ValueError("Large-market validation summary must be for Atlanta_GA_L")
    reference_recall = _mapping(
        summary.get("reference_recall"), "Atlanta reference recall"
    )
    decision = str(reference_recall.get("decision", "")).strip()
    if decision not in {"approve_as_primary", "maps_supplement_required"}:
        raise ValueError("Atlanta reference recall does not permit standard rollout")
    recall = float(reference_recall.get("overall_recall", 0.0))
    if recall < 0.90:
        raise ValueError("Atlanta reference recall is below the frozen 0.90 gate")
    universe = _mapping(
        summary.get("legacy_reference_universe"), "Atlanta reference universe"
    )
    if universe.get("recall_denominator") != "eligible_target_zip_units_only":
        raise ValueError("Atlanta recall denominator is not target-ZIP comparable")
    reference_count = int(reference_recall.get("reference_count", 0))
    eligible_count = int(universe.get("eligible_target_zip_units", 0))
    if reference_count <= 0 or reference_count != eligible_count:
        raise ValueError("Atlanta reference denominator counts do not agree")
    if int(summary.get("completed_paid_requests", 0)) < 2:
        raise ValueError("Atlanta validation does not contain completed paid requests")
    return {
        "market": "Atlanta_GA_L",
        "overall_recall": recall,
        "decision": decision,
        "reference_count": reference_count,
        "recall_denominator": universe["recall_denominator"],
    }


def _boolean_series(series: pd.Series, label: str) -> pd.Series:
    normalized = series.astype(str).str.strip().str.lower()
    if not normalized.isin({"true", "false"}).all():
        raise ValueError(f"{label} must contain only true or false")
    return normalized.eq("true")


def validate_rollout_first_page_plan(plan: pd.DataFrame) -> pd.DataFrame:
    """Validate the frozen planning output before selecting a paid stage."""

    missing = REQUIRED_ROLLOUT_PLAN_COLUMNS - set(plan.columns)
    if missing:
        raise KeyError(f"Rollout plan is missing columns: {sorted(missing)}")
    result = plan.copy()
    tags = result["task_tag"].astype("string").str.strip()
    if tags.isna().any() or tags.eq("").any() or tags.duplicated().any():
        raise ValueError("Rollout task tags must be nonblank and unique")
    result["task_tag"] = tags
    if len(result) != 26 or result["market"].nunique() != 13:
        raise ValueError("Frozen rollout plan must contain 26 requests for 13 markets")
    if not _boolean_series(result["planning_only"], "planning_only").all():
        raise ValueError("Rollout plan must retain planning_only=true")
    if _boolean_series(result["execution_enabled"], "execution_enabled").any():
        raise ValueError("Rollout plan must retain execution_enabled=false")
    if not pd.to_numeric(result["page_number"], errors="coerce").eq(1).all():
        raise ValueError("Rollout first-page plan must contain page_number=1 only")
    if not pd.to_numeric(result["limit"], errors="coerce").eq(1000).all():
        raise ValueError("Rollout first-page plan must retain limit=1000")
    for row in result.itertuples(index=False):
        categories = parse_category_cell(row.categories)
        if len(categories) != int(row.category_count):
            raise ValueError("Rollout category_count does not match categories")
    if not result.groupby("market").size().eq(2).all():
        raise ValueError("Each rollout market must contain exactly two category groups")
    if not result.groupby("market")["category_count"].sum().eq(13).all():
        raise ValueError("Each rollout market must cover all 13 categories")
    return result.reset_index(drop=True)


def select_next_paid_rollout_stage(
    plan: pd.DataFrame,
    stage: str,
    *,
    standard_rollout_approved: bool = False,
) -> pd.DataFrame:
    """Select Atlanta validation or the approved ten-market standard rollout."""

    validated = validate_rollout_first_page_plan(plan)
    clean_stage = str(stage).strip()
    if clean_stage not in {"large_market_validation", "standard_rollout"}:
        raise ValueError(
            "Only large_market_validation or standard_rollout can be selected"
        )
    if clean_stage == "standard_rollout" and not standard_rollout_approved:
        raise ValueError(
            "standard_rollout requires an approved corrected Atlanta comparison"
        )
    selected = validated.loc[validated["stage"].eq(clean_stage)].copy()
    if clean_stage == "large_market_validation":
        if len(selected) != 2 or set(selected["market"].astype(str)) != {"Atlanta_GA_L"}:
            raise ValueError("Large-market validation must contain two Atlanta requests")
        if not selected["execution_status"].eq("next_validation").all():
            raise ValueError("Atlanta requests must retain next_validation status")
    else:
        if len(selected) != 20 or selected["market"].nunique() != 10:
            raise ValueError("Standard rollout must contain 20 requests for 10 markets")
        if not selected["execution_status"].eq(
            "conditional_after_large_market_validation"
        ).all():
            raise ValueError("Standard rollout requests have an unexpected status")
    return selected.reset_index(drop=True)


def select_major_metro_probe(
    plan: pd.DataFrame,
    reference_coverage: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Select only the four NYC/LA first-page requests after coverage checks."""

    validated = validate_rollout_first_page_plan(plan)
    selected = validated.loc[validated["stage"].eq("major_metro_review")].copy()
    expected_markets = {"NYC_NY_L", "LA_CA_L"}
    if len(selected) != 4 or set(selected["market"].astype(str)) != expected_markets:
        raise ValueError("Major-metro probe must contain four NYC/LA requests")
    if not selected["execution_status"].eq("geometry_and_pagination_review").all():
        raise ValueError("Major-metro requests have an unexpected execution status")

    required = {
        "clinic_key",
        "search_location",
        "distance_from_hub_km",
        "planned_radius_km",
        "inside_planned_radius",
    }
    missing = required - set(reference_coverage.columns)
    if missing:
        raise KeyError(f"Reference coverage is missing columns: {sorted(missing)}")
    coverage = reference_coverage.loc[
        reference_coverage["search_location"].astype(str).isin(expected_markets)
    ].copy()
    if set(coverage["search_location"].astype(str)) != expected_markets:
        raise ValueError("Reference coverage must contain both NYC and LA")
    if coverage["clinic_key"].astype(str).duplicated().any():
        raise ValueError("Major-metro reference coverage contains duplicate clinic_key")
    inside = _boolean_series(coverage["inside_planned_radius"], "inside_planned_radius")
    if not inside.all():
        raise ValueError("A corrected legacy NYC/LA reference lies outside the probe radius")

    evidence: dict[str, Any] = {}
    for market, group in coverage.groupby("search_location", sort=True):
        planned_radii = pd.to_numeric(group["planned_radius_km"], errors="raise").unique()
        request_radii = pd.to_numeric(
            selected.loc[selected["market"].eq(market), "radius_km"], errors="raise"
        ).unique()
        if len(planned_radii) != 1 or len(request_radii) != 1:
            raise ValueError(f"{market} must use one frozen probe radius")
        if float(planned_radii[0]) != float(request_radii[0]):
            raise ValueError(f"{market} plan and reference coverage radii disagree")
        evidence[str(market)] = {
            "zip_valid_reference_clinics": len(group),
            "maximum_reference_distance_km": round(
                float(pd.to_numeric(group["distance_from_hub_km"], errors="raise").max()),
                4,
            ),
            "probe_radius_km": float(planned_radii[0]),
            "outside_probe_radius": 0,
        }
    return selected.reset_index(drop=True), evidence


def audit_major_metro_first_pages(
    observations: pd.DataFrame,
    group_completeness: pd.DataFrame,
    regions_config: Mapping[str, Any],
    *,
    request_cost_usd: float,
    item_cost_usd: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Measure target-ZIP yield before paying for major-metro continuations."""

    markets = {"NYC_NY_L", "LA_CA_L"}
    required_observations = {
        "task_tag",
        "requested_location",
        "cid",
        "place_id",
        "zip",
    }
    missing = required_observations - set(observations.columns)
    if missing:
        raise KeyError(f"Major-metro observations are missing: {sorted(missing)}")
    work = observations.loc[
        observations["requested_location"].astype(str).isin(markets)
    ].copy()
    if work.empty or set(work["requested_location"].astype(str)) != markets:
        raise ValueError("Major-metro observations must contain both NYC and LA")
    extracted = work["task_tag"].astype(str).str.extract(r":g(\d+):p01$")[0]
    if extracted.isna().any():
        raise ValueError("Major-metro scope audit accepts first-page task tags only")
    work["category_group"] = extracted.astype(int)
    if set(work["category_group"]) != {1, 2}:
        raise ValueError("Each major metro must contain category groups 1 and 2")

    regions = _mapping(regions_config.get("regions"), "regions")
    work["normalized_zip"] = work["zip"].map(normalize_zip)
    work["inside_target_zip"] = [
        _zip_in_region(zip_code, _mapping(regions[market], market))
        for zip_code, market in zip(
            work["normalized_zip"], work["requested_location"]
        )
    ]
    profile_keys: list[str] = []
    for cid, place_id in zip(work["cid"], work["place_id"]):
        clean_cid = str(cid).strip() if pd.notna(cid) else ""
        clean_place = str(place_id).strip() if pd.notna(place_id) else ""
        if clean_cid:
            profile_keys.append(f"google:cid:{clean_cid}")
        elif clean_place:
            profile_keys.append(f"google:place_id:{clean_place}")
        else:
            raise ValueError("Major-metro observation lacks both cid and place_id")
    work["profile_key"] = profile_keys

    required_groups = {
        "market",
        "category_group",
        "reported_total_count",
        "saved_items_across_pages",
        "category_group_complete",
    }
    missing = required_groups - set(group_completeness.columns)
    if missing:
        raise KeyError(f"Pagination groups are missing: {sorted(missing)}")
    groups = group_completeness.loc[
        group_completeness["market"].astype(str).isin(markets)
    ].copy()
    if len(groups) != 4 or set(groups["market"].astype(str)) != markets:
        raise ValueError("Pagination audit must contain four NYC/LA category groups")
    if groups[["market", "category_group"]].duplicated().any():
        raise ValueError("Pagination audit contains duplicate major-metro groups")

    records: list[dict[str, Any]] = []
    for row in groups.itertuples(index=False):
        market = str(row.market)
        category_group = int(row.category_group)
        sample = work.loc[
            work["requested_location"].eq(market)
            & work["category_group"].eq(category_group)
        ]
        saved_items = int(row.saved_items_across_pages)
        if len(sample) != saved_items:
            raise ValueError("Parsed first-page rows disagree with pagination audit")
        total = int(row.reported_total_count)
        remaining = max(total - saved_items, 0)
        additional_requests = ceil(remaining / 1000) if remaining else 0
        target = int(sample["inside_target_zip"].sum())
        missing_zip = int(sample["normalized_zip"].isna().sum())
        records.append(
            {
                "market": market,
                "category_group": category_group,
                "reported_total_count": total,
                "first_page_items": len(sample),
                "first_page_unique_profiles": int(sample["profile_key"].nunique()),
                "first_page_target_zip_items": target,
                "first_page_outside_target_zip_items": len(sample) - target - missing_zip,
                "first_page_missing_zip_items": missing_zip,
                "first_page_target_zip_share": target / len(sample),
                "remaining_reported_items": remaining,
                "estimated_additional_requests": additional_requests,
                "estimated_blind_continuation_cost_usd": round(
                    remaining * float(item_cost_usd)
                    + additional_requests * float(request_cost_usd),
                    6,
                ),
                "recommended_next_action": (
                    "review_filter_or_partition_before_continuation"
                    if total > 10000
                    else "bounded_continuation_candidate"
                ),
            }
        )
    group_scope = pd.DataFrame.from_records(records).sort_values(
        ["market", "category_group"], ignore_index=True
    )
    overlaps: dict[str, int] = {}
    for market, sample in work.groupby("requested_location", sort=True):
        group_one = set(sample.loc[sample["category_group"].eq(1), "profile_key"])
        group_two = set(sample.loc[sample["category_group"].eq(2), "profile_key"])
        overlaps[str(market)] = len(group_one & group_two)
    summary = {
        "analysis_status": "major_metro_first_page_scope_audit_not_final",
        "api_requests_submitted": 0,
        "markets_audited": sorted(markets),
        "first_page_observations": len(work),
        "first_page_target_zip_items": int(work["inside_target_zip"].sum()),
        "first_page_target_zip_share": float(work["inside_target_zip"].mean()),
        "cross_category_group_exact_profile_overlap": overlaps,
        "reported_total_items": int(group_scope["reported_total_count"].sum()),
        "remaining_reported_items": int(group_scope["remaining_reported_items"].sum()),
        "estimated_blind_continuation_cost_usd": round(
            float(group_scope["estimated_blind_continuation_cost_usd"].sum()), 6
        ),
        "groups_over_numeric_offset_guidance": int(
            group_scope["reported_total_count"].gt(10000).sum()
        ),
        "automatic_continuation_requests_submitted": 0,
        "interpretation_limit": (
            "First-page ordering may differ from later pages. Target-ZIP yield is a "
            "waste diagnostic, not an unbiased estimate of final target-ZIP recall."
        ),
    }
    return work.reset_index(drop=True), group_scope, summary


def build_major_metro_filtered_count_plan(
    plan: pd.DataFrame,
    plan_config: Mapping[str, Any],
    regions_config: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build four limit-one ZIP-filtered requests for total-count validation."""

    selected = validate_rollout_first_page_plan(plan)
    selected = selected.loc[selected["stage"].eq("major_metro_review")].copy()
    markets = {"NYC_NY_L", "LA_CA_L"}
    if len(selected) != 4 or set(selected["market"].astype(str)) != markets:
        raise ValueError("Filtered count probe requires four NYC/LA source requests")
    rollout = _mapping(plan_config.get("business_listings_rollout"), "rollout")
    regexes = _mapping(
        rollout.get("major_metro_target_zip_regex"), "major metro ZIP regex"
    )
    if set(regexes) != markets:
        raise ValueError("Major-metro ZIP regex must contain exactly NYC and LA")
    regions = _mapping(regions_config.get("regions"), "regions")
    for market in sorted(markets):
        pattern = re.compile(str(regexes[market]))
        region = _mapping(regions[market], market)
        expected: set[str] = set()
        for value in region.get("zip_values", []):
            expected.add(f"{int(value):05d}")
        for lower, upper in region.get("zip_ranges", []):
            expected.update(f"{value:05d}" for value in range(int(lower), int(upper) + 1))
        matched = {f"{value:05d}" for value in range(100000) if pattern.fullmatch(f"{value:05d}")}
        if matched != expected:
            raise ValueError(f"{market} ZIP regex does not exactly match regions.yaml")

    pricing = _mapping(plan_config.get("pricing"), "pricing")
    request_cost = float(pricing["business_listings_live_per_request"])
    item_cost = float(pricing["business_listings_live_per_item"])
    selected["source_task_tag"] = selected["task_tag"]
    selected["task_tag"] = selected.apply(
        lambda row: (
            "business_listings_major_metro_filter_count:"
            f"{row['market']}:g{int(row['category_group']):02d}:p01"
        ),
        axis=1,
    )
    selected["limit"] = 1
    selected["filters_json"] = selected["market"].map(
        lambda market: json.dumps(
            [["address_info.zip", "regex", str(regexes[str(market)])]],
            separators=(",", ":"),
        )
    )
    selected["estimated_cost_usd"] = request_cost + item_cost
    selected["planning_only"] = True
    selected["execution_enabled"] = False
    summary = {
        "analysis_status": "major_metro_zip_filtered_count_plan",
        "planning_only": True,
        "paid_execution_enabled": False,
        "markets": sorted(markets),
        "planned_requests": len(selected),
        "limit_per_request": 1,
        "estimated_total_cost_usd": round(
            float(selected["estimated_cost_usd"].sum()), 6
        ),
        "filter_field": "address_info.zip",
        "automatic_continuation_requests_submitted": 0,
    }
    return selected.reset_index(drop=True), summary


def build_major_metro_filtered_page_plan(
    plan: pd.DataFrame,
    count_log: pd.DataFrame,
    plan_config: Mapping[str, Any],
    regions_config: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Turn four completed ZIP-filtered count probes into token page chains."""

    count_plan, _ = build_major_metro_filtered_count_plan(
        plan, plan_config, regions_config
    )
    required = {"task_tag", "request_status", "total_count", "item_count"}
    missing = required - set(count_log.columns)
    if missing:
        raise KeyError(f"Filtered count log is missing columns: {sorted(missing)}")
    completed = count_log.loc[count_log["request_status"].eq("completed")].copy()
    expected_tags = set(count_plan["task_tag"].astype(str))
    unexpected = set(completed["task_tag"].astype(str)) - expected_tags
    if unexpected:
        raise ValueError(f"Filtered count log contains unexpected tags: {sorted(unexpected)}")
    duplicated = completed["task_tag"].astype(str).duplicated(keep=False)
    if duplicated.any():
        raise ValueError("Filtered count log contains duplicate completed probes")
    if set(completed["task_tag"].astype(str)) != expected_tags:
        raise ValueError("All four ZIP-filtered count probes must be completed")
    counts = completed.set_index(completed["task_tag"].astype(str))
    totals = pd.to_numeric(counts["total_count"], errors="raise").astype(int)
    returned = pd.to_numeric(counts["item_count"], errors="raise").astype(int)
    if totals.lt(0).any() or returned.ne(1).any():
        raise ValueError("Filtered count probes must return one item and nonnegative totals")

    pricing = _mapping(plan_config.get("pricing"), "pricing")
    request_cost = float(pricing["business_listings_live_per_request"])
    item_cost = float(pricing["business_listings_live_per_item"])
    page_limit = int(pricing["business_listings_maximum_items_per_request"])
    if page_limit != 1000:
        raise ValueError("Major-metro token pagination requires the frozen 1000-item limit")

    result = count_plan.copy()
    result["count_probe_task_tag"] = result["task_tag"]
    result["api_task_tag"] = result.apply(
        lambda row: (
            "business_listings_major_metro_zip_filtered:"
            f"{row['market']}:g{int(row['category_group']):02d}"
        ),
        axis=1,
    )
    result["group_id"] = result.apply(
        lambda row: f"{row['market']}:g{int(row['category_group']):02d}", axis=1
    )
    result["audited_total_count"] = result["count_probe_task_tag"].map(totals)
    result["planned_page_count"] = result["audited_total_count"].map(
        lambda value: int(ceil(int(value) / page_limit)) if int(value) else 0
    )
    result["limit"] = page_limit
    result["estimated_cost_usd"] = (
        result["planned_page_count"] * request_cost
        + result["audited_total_count"] * item_cost
    )
    result["planning_only"] = True
    result["execution_enabled"] = False
    result = result.drop(columns=["task_tag"])
    summary = {
        "analysis_status": "major_metro_zip_filtered_token_page_plan",
        "planning_only": True,
        "paid_execution_enabled": False,
        "markets": sorted(result["market"].astype(str).unique()),
        "category_groups": len(result),
        "audited_filtered_items": int(result["audited_total_count"].sum()),
        "planned_page_requests": int(result["planned_page_count"].sum()),
        "limit_per_request": page_limit,
        "pagination_method": "offset_token_chain",
        "estimated_total_cost_usd": round(float(result["estimated_cost_usd"].sum()), 6),
        "automatic_unplanned_requests_submitted": 0,
    }
    return result.reset_index(drop=True), summary


def audit_major_metro_filtered_page_log(
    page_log: pd.DataFrame,
    group_plan: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate saved token chains and return resumable state for every group."""

    required_plan = {
        "group_id",
        "market",
        "category_group",
        "audited_total_count",
        "planned_page_count",
    }
    missing_plan = required_plan - set(group_plan.columns)
    if missing_plan:
        raise KeyError(f"Filtered page plan is missing columns: {sorted(missing_plan)}")
    if group_plan["group_id"].astype(str).duplicated().any():
        raise ValueError("Filtered page plan contains duplicate group_id values")

    required_log = {
        "page_request_tag",
        "group_id",
        "page_number",
        "request_status",
        "item_count",
        "total_count",
        "offset_token_used",
        "next_offset_token",
    }
    if page_log.empty:
        latest = pd.DataFrame(columns=sorted(required_log))
    else:
        missing_log = required_log - set(page_log.columns)
        if missing_log:
            raise KeyError(f"Filtered page log is missing columns: {sorted(missing_log)}")
        latest = page_log.drop_duplicates("page_request_tag", keep="last").copy()
        latest = latest.loc[latest["request_status"].eq("completed")].copy()
        unexpected = set(latest["group_id"].astype(str)) - set(
            group_plan["group_id"].astype(str)
        )
        if unexpected:
            raise ValueError(f"Filtered page log contains unexpected groups: {sorted(unexpected)}")

    records: list[dict[str, Any]] = []
    drift_groups: list[str] = []
    for source in group_plan.sort_values(["market", "category_group"]).to_dict(
        orient="records"
    ):
        group_id = str(source["group_id"])
        pages = latest.loc[latest["group_id"].astype(str).eq(group_id)].copy()
        if pages.empty:
            records.append(
                {
                    **source,
                    "completed_pages": 0,
                    "saved_items": 0,
                    "latest_total_count": int(source["audited_total_count"]),
                    "next_offset_token": None,
                    "group_complete": int(source["audited_total_count"]) == 0,
                    "remaining_planned_requests": int(source["planned_page_count"]),
                    "total_count_drift": False,
                }
            )
            continue
        pages["page_number"] = pd.to_numeric(
            pages["page_number"], errors="raise"
        ).astype(int)
        pages = pages.sort_values("page_number")
        expected_numbers = list(range(1, len(pages) + 1))
        if pages["page_number"].tolist() != expected_numbers:
            raise ValueError(f"{group_id} completed pages are not contiguous from page 1")
        if pages["page_number"].duplicated().any():
            raise ValueError(f"{group_id} contains duplicate completed page numbers")
        used_tokens = pages["offset_token_used"].fillna("").astype(str).tolist()
        next_tokens = pages["next_offset_token"].fillna("").astype(str).tolist()
        if used_tokens[0]:
            raise ValueError(f"{group_id} page 1 must not use an offset token")
        for index in range(1, len(pages)):
            if not next_tokens[index - 1] or used_tokens[index] != next_tokens[index - 1]:
                raise ValueError(f"{group_id} offset-token chain is broken")
        nonblank_used = [value for value in used_tokens if value]
        if len(nonblank_used) != len(set(nonblank_used)):
            raise ValueError(f"{group_id} reuses an offset token")
        item_counts = pd.to_numeric(pages["item_count"], errors="raise").astype(int)
        totals_seen = pd.to_numeric(pages["total_count"], errors="raise").astype(int)
        if item_counts.lt(0).any() or item_counts.gt(int(source.get("limit", 1000))).any():
            raise ValueError(f"{group_id} contains an invalid page item count")
        saved_items = int(item_counts.sum())
        latest_total = int(totals_seen.iloc[-1])
        final_token = next_tokens[-1] or None
        complete = saved_items >= latest_total
        if not complete and final_token is None:
            raise ValueError(
                f"{group_id} has not covered total_count and has no continuation token"
            )
        if not complete and item_counts.iloc[-1] == 0:
            raise ValueError(f"{group_id} returned an empty page before completion")
        drift = bool(totals_seen.ne(int(source["audited_total_count"])).any())
        if drift:
            drift_groups.append(group_id)
        required_pages = int(ceil(latest_total / int(source.get("limit", 1000)))) if latest_total else 0
        remaining = 0 if complete else max(0, required_pages - len(pages))
        records.append(
            {
                **source,
                "completed_pages": len(pages),
                "saved_items": saved_items,
                "latest_total_count": latest_total,
                "next_offset_token": final_token,
                "group_complete": complete,
                "remaining_planned_requests": remaining,
                "total_count_drift": drift,
            }
        )
    state = pd.DataFrame.from_records(records)
    summary = {
        "analysis_status": "major_metro_zip_filtered_token_page_state",
        "category_groups": len(state),
        "completed_groups": int(state["group_complete"].sum()),
        "completed_page_requests": int(state["completed_pages"].sum()),
        "saved_items": int(state["saved_items"].sum()),
        "remaining_planned_requests": int(state["remaining_planned_requests"].sum()),
        "total_count_drift_groups": sorted(drift_groups),
    }
    return state, summary


def build_rollout_continuation_plan(
    first_page_plan: pd.DataFrame,
    page_completeness: pd.DataFrame,
    *,
    request_cost_usd: float,
    item_cost_usd: float,
    maximum_offset: int = 10000,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Plan bounded offset pages from an audited first-page response."""

    validated = validate_rollout_first_page_plan(first_page_plan)
    required = {
        "task_tag",
        "market",
        "category_group",
        "total_count",
        "returned_item_count",
        "requested_offset",
        "next_offset",
        "pagination_required",
        "continuation_available",
    }
    missing = required - set(page_completeness.columns)
    if missing:
        raise KeyError(f"Page completeness is missing columns: {sorted(missing)}")
    audit = page_completeness.copy()
    if audit["task_tag"].astype(str).duplicated().any():
        raise ValueError("Page completeness contains duplicate task tags")
    plan_tags = set(validated["task_tag"].astype(str))
    audit_tags = set(audit["task_tag"].astype(str))
    continuation_tags: set[str] = set()
    for tag in audit_tags - plan_tags:
        prefix, separator, page_text = tag.rpartition(":p")
        if (
            separator
            and page_text.isdigit()
            and int(page_text) >= 2
            and f"{prefix}:p01" in plan_tags
        ):
            continuation_tags.add(tag)
    unknown = audit_tags - plan_tags - continuation_tags
    if unknown:
        raise ValueError(f"Page completeness contains unknown task tags: {sorted(unknown)}")
    group_audit = audit_business_listings_page_groups(audit)
    incomplete_groups = group_audit.loc[
        ~group_audit["category_group_complete"].astype(bool),
        ["market", "category_group"],
    ].copy()
    first_pages = audit.loc[
        pd.to_numeric(audit["requested_offset"], errors="raise").eq(0)
    ].copy()
    required_pages = first_pages.merge(
        incomplete_groups,
        on=["market", "category_group"],
        how="inner",
        validate="one_to_one",
    )
    if required_pages.empty:
        raise ValueError("No audited first-page request requires continuation")
    if not _boolean_series(
        required_pages["pagination_required"], "pagination_required"
    ).all():
        raise ValueError("An incomplete category group lacks first-page pagination evidence")
    if not _boolean_series(
        required_pages["continuation_available"], "continuation_available"
    ).all():
        raise ValueError("A required continuation is unavailable")

    source_by_tag = validated.set_index("task_tag", drop=False)
    records: list[dict[str, Any]] = []
    for audit_row in required_pages.to_dict(orient="records"):
        source = source_by_tag.loc[str(audit_row["task_tag"])]
        total_count = int(audit_row["total_count"])
        returned = int(audit_row["returned_item_count"])
        requested_offset = int(audit_row["requested_offset"])
        next_offset = int(audit_row["next_offset"])
        limit = int(source["limit"])
        if requested_offset != 0 or next_offset != returned:
            raise ValueError("Continuation planning requires an audited first page")
        if total_count <= returned:
            raise ValueError("Continuation total_count must exceed returned items")
        if total_count > int(maximum_offset):
            raise ValueError("Result set exceeds the approved numeric-offset limit")
        offsets = list(range(next_offset, total_count, limit))
        for page_number, offset in enumerate(offsets, start=2):
            expected_items = min(limit, total_count - offset)
            original_tag = str(source["task_tag"])
            if not original_tag.endswith(":p01"):
                raise ValueError("First-page task tag must end with :p01")
            record = source.to_dict()
            record.update(
                {
                    "task_tag": f"{original_tag[:-3]}p{page_number:02d}",
                    "page_number": page_number,
                    "offset": offset,
                    "source_first_page_tag": original_tag,
                    "audited_total_count": total_count,
                    "expected_page_items": expected_items,
                    "estimated_minimum_cost_usd": round(float(request_cost_usd), 6),
                    "estimated_expected_cost_usd": round(
                        float(request_cost_usd) + expected_items * float(item_cost_usd),
                        6,
                    ),
                    "continuation_basis": "numeric_offset_total_below_10000",
                    "planning_only": True,
                    "execution_enabled": False,
                }
            )
            records.append(record)
    continuation = pd.DataFrame.from_records(records)
    if continuation.empty or continuation["task_tag"].duplicated().any():
        raise ValueError("Continuation plan must contain unique requests")
    summary = {
        "analysis_status": "audited_bounded_continuation_plan",
        "source_requests_requiring_continuation": len(required_pages),
        "planned_continuation_requests": len(continuation),
        "planned_offsets": continuation["offset"].astype(int).tolist(),
        "expected_remaining_items": int(continuation["expected_page_items"].sum()),
        "estimated_minimum_cost_usd": round(
            float(continuation["estimated_minimum_cost_usd"].sum()), 6
        ),
        "estimated_expected_cost_usd": round(
            float(continuation["estimated_expected_cost_usd"].sum()), 6
        ),
        "maximum_offset": int(maximum_offset),
        "paid_execution_enabled": False,
    }
    return continuation, summary


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _sequence(value: object, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{label} must be a sequence")
    result = [str(item).strip() for item in value]
    if not result or any(not item for item in result):
        raise ValueError(f"{label} cannot be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def _distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    latitude_delta = radians(latitude_b - latitude_a)
    longitude_delta = radians(longitude_b - longitude_a)
    value = (
        sin(latitude_delta / 2) ** 2
        + cos(radians(latitude_a))
        * cos(radians(latitude_b))
        * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(value))


def _normalize_zip(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return f"{int(float(text)):05d}"
    except ValueError:
        digits = "".join(character for character in text if character.isdigit())
        return digits[:5] if len(digits) >= 5 else None


def _zip_in_region(zip_code: str | None, region: Mapping[str, Any]) -> bool:
    if zip_code is None or pd.isna(zip_code):
        return False
    numeric = int(zip_code)
    values = {int(value) for value in region.get("zip_values", [])}
    ranges = region.get("zip_ranges", [])
    return numeric in values or any(
        int(lower) <= numeric <= int(upper) for lower, upper in ranges
    )


def build_rollout_first_page_plan(
    plan_config: Mapping[str, Any],
    regions_config: Mapping[str, Any],
    category_catalog: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build a non-executable first-page plan for the remaining 13 markets."""

    rollout = _mapping(plan_config.get("business_listings_rollout"), "rollout")
    if rollout.get("planning_only") is not True:
        raise ValueError("Rollout must set planning_only: true")
    if rollout.get("execution_enabled") is not False:
        raise ValueError("Rollout must set execution_enabled: false")
    regions = _mapping(regions_config.get("regions"), "regions")
    validated = set(
        _sequence(rollout.get("validated_pilot_markets"), "validated markets")
    )
    large_validation = str(rollout.get("large_market_validation_market", "")).strip()
    major_metros = set(
        _sequence(rollout.get("major_metro_review_markets"), "major metro markets")
    )
    if not large_validation or large_validation in validated:
        raise ValueError("Large-market validation market is invalid")
    radii = _mapping(rollout.get("market_radii_km"), "market radii")
    if set(radii) != set(regions):
        raise ValueError("Rollout radii must cover every configured region exactly")
    requested = validate_official_categories(
        category_catalog,
        rollout.get("requested_categories", []),
    )
    group_size = int(rollout.get("maximum_categories_per_request", 0))
    if not 1 <= group_size <= 10:
        raise ValueError("maximum_categories_per_request must be between 1 and 10")
    groups = [requested[index : index + group_size] for index in range(0, len(requested), group_size)]
    pricing = _mapping(plan_config.get("pricing"), "pricing")
    request_cost = float(pricing["business_listings_live_per_request"])
    item_cost = float(pricing["business_listings_live_per_item"])
    limit = int(pricing["business_listings_maximum_items_per_request"])

    records: list[dict[str, Any]] = []
    for market, region_value in regions.items():
        if market in validated:
            continue
        region = _mapping(region_value, market)
        hub = region.get("hub")
        if not isinstance(hub, Sequence) or len(hub) != 2:
            raise ValueError(f"{market} requires a two-value hub")
        radius = float(radii[market])
        if not 1 <= radius <= 100000:
            raise ValueError(f"Invalid radius for {market}")
        if market == large_validation:
            stage = "large_market_validation"
            status = "next_validation"
        elif market in major_metros:
            stage = "major_metro_review"
            status = "geometry_and_pagination_review"
        else:
            stage = "standard_rollout"
            status = "conditional_after_large_market_validation"
        coordinate = f"{float(hub[0]):.7f},{float(hub[1]):.7f},{radius:g}"
        for group_number, categories in enumerate(groups, start=1):
            records.append(
                {
                    "task_tag": f"business_listings_rollout:{market}:g{group_number:02d}:p01",
                    "stage": stage,
                    "execution_status": status,
                    "market": market,
                    "category_group": group_number,
                    "categories": "|".join(categories),
                    "category_count": len(categories),
                    "location_coordinate": coordinate,
                    "radius_km": radius,
                    "limit": limit,
                    "page_number": 1,
                    "estimated_minimum_cost_usd": round(request_cost, 6),
                    "estimated_maximum_cost_usd": round(request_cost + limit * item_cost, 6),
                    "planning_only": True,
                    "execution_enabled": False,
                }
            )
    plan = pd.DataFrame.from_records(records)
    if plan.empty or plan["task_tag"].duplicated().any():
        raise ValueError("Rollout plan requires unique nonempty task tags")
    stage_counts = plan.groupby("stage").size().astype(int).to_dict()
    summary = {
        "analysis_status": "staged_rollout_planning_only",
        "api_credentials_read": False,
        "api_requests_submitted": 0,
        "validated_pilot_markets": sorted(validated),
        "remaining_market_count": int(plan["market"].nunique()),
        "requested_category_count": len(requested),
        "category_groups_per_market": len(groups),
        "planned_first_page_requests": len(plan),
        "requests_by_stage": stage_counts,
        "estimated_first_page_minimum_cost_usd": round(float(plan["estimated_minimum_cost_usd"].sum()), 4),
        "estimated_first_page_maximum_cost_usd": round(float(plan["estimated_maximum_cost_usd"].sum()), 4),
        "next_paid_stage": {
            "market": large_validation,
            "request_count": int((plan["stage"] == "large_market_validation").sum()),
        },
        "major_metro_review_markets": sorted(major_metros),
        "paid_execution_enabled": False,
    }
    return plan, summary


def audit_rollout_reference_envelope(
    clinics: pd.DataFrame,
    plan: pd.DataFrame,
    regions_config: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Check planned circles against ZIP-valid corrected legacy clinics."""

    required = {"clinic_key", "search_location", "zip", "latitude", "longitude"}
    missing = required - set(clinics.columns)
    if missing:
        raise KeyError(f"Clinics are missing columns: {sorted(missing)}")
    regions = _mapping(regions_config.get("regions"), "regions")
    radius_by_market = plan.groupby("market")["radius_km"].first().to_dict()
    work = clinics.loc[clinics["search_location"].isin(radius_by_market)].copy()
    if "spatial_analysis_eligible" in work.columns:
        eligible = work["spatial_analysis_eligible"].astype(str).str.lower().isin({"true", "1"})
        work = work.loc[eligible].copy()
    work["normalized_zip"] = work["zip"].map(_normalize_zip)
    work["inside_target_zip_rule"] = [
        _zip_in_region(zip_code, _mapping(regions[market], market))
        for zip_code, market in zip(work["normalized_zip"], work["search_location"])
    ]
    work = work.loc[work["inside_target_zip_rule"]].copy()
    if work["clinic_key"].astype(str).duplicated().any():
        raise ValueError("ZIP-valid rollout references contain duplicate clinic_key values")
    work["latitude"] = pd.to_numeric(work["latitude"], errors="coerce")
    work["longitude"] = pd.to_numeric(work["longitude"], errors="coerce")
    work = work.dropna(subset=["latitude", "longitude"])
    distances: list[float] = []
    radii: list[float] = []
    for row in work.itertuples(index=False):
        region = _mapping(regions[row.search_location], row.search_location)
        hub = region["hub"]
        distances.append(
            _distance_km(float(hub[0]), float(hub[1]), float(row.latitude), float(row.longitude))
        )
        radii.append(float(radius_by_market[row.search_location]))
    work["distance_from_hub_km"] = distances
    work["planned_radius_km"] = radii
    work["inside_planned_radius"] = work["distance_from_hub_km"] <= work["planned_radius_km"]
    output = work[
        [
            "clinic_key",
            "search_location",
            "normalized_zip",
            "latitude",
            "longitude",
            "distance_from_hub_km",
            "planned_radius_km",
            "inside_planned_radius",
        ]
    ].sort_values(["search_location", "clinic_key"], ignore_index=True)
    if output.empty:
        raise ValueError("No ZIP-valid rollout reference clinics remain")
    markets: dict[str, dict[str, Any]] = {}
    for market, group in output.groupby("search_location", sort=True):
        markets[str(market)] = {
            "zip_valid_reference_clinics": len(group),
            "maximum_reference_distance_km": round(float(group["distance_from_hub_km"].max()), 4),
            "planned_radius_km": float(group["planned_radius_km"].iloc[0]),
            "outside_planned_radius": int((~group["inside_planned_radius"]).sum()),
        }
    markets_without_reference = sorted(set(radius_by_market) - set(markets))
    summary = {
        "zip_valid_reference_clinics": len(output),
        "outside_planned_radius": int((~output["inside_planned_radius"]).sum()),
        "all_zip_valid_references_inside_planned_radius": bool(output["inside_planned_radius"].all()),
        "markets_without_reference": markets_without_reference,
        "reference_envelope_complete": bool(
            output["inside_planned_radius"].all() and not markets_without_reference
        ),
        "markets": markets,
        "coverage_limit": "This checks known corrected legacy clinics, not every geographic point inside each ZIP rule.",
    }
    return output, summary
