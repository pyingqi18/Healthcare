"""Validate and summarize planning-only full-market scrape profiles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd


SUPPORTED_METHODS = {
    "business_listings_live",
    "google_maps_standard",
}


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _positive_int(value: object, label: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"{label} must be positive")
    return parsed


def _unique_strings(value: object, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{label} must be a sequence")
    parsed = [str(item).strip() for item in value]
    if not parsed or any(not item for item in parsed):
        raise ValueError(f"{label} cannot be empty")
    if len(parsed) != len(set(parsed)):
        raise ValueError(f"{label} contains duplicates")
    return parsed


def build_scrape_profile_plan(
    plan_config: Mapping[str, Any],
    regions_config: Mapping[str, Any],
    *,
    profile_name: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build a costed plan without constructing or submitting API requests."""

    profiles = _mapping(plan_config.get("profiles"), "profiles")
    profile = _mapping(profiles.get(profile_name), f"profile {profile_name}")
    if profile.get("planning_only") is not True:
        raise ValueError("Scrape planning profile must set planning_only: true")
    if profile.get("execution_enabled") is not False:
        raise ValueError("Scrape planning profile must disable execution")

    regions = _mapping(regions_config.get("regions"), "regions")
    profile_markets = _unique_strings(profile.get("markets"), "profile markets")
    unknown_markets = sorted(set(profile_markets) - set(regions))
    if unknown_markets:
        raise KeyError(f"Unknown profile markets: {unknown_markets}")

    pricing = _mapping(plan_config.get("pricing"), "pricing")
    maps_price = float(pricing["google_maps_standard_per_100_results"])
    finder_page_price = float(
        pricing["google_local_finder_standard_per_20_results"]
    )
    listing_request_price = float(
        pricing["business_listings_live_per_request"]
    )
    listing_item_price = float(pricing["business_listings_live_per_item"])
    if min(maps_price, finder_page_price, listing_request_price, listing_item_price) < 0:
        raise ValueError("Pricing values cannot be negative")

    rows: list[dict[str, Any]] = []
    phases = profile.get("phases")
    if not isinstance(phases, Sequence) or isinstance(phases, (str, bytes)):
        raise TypeError("profile phases must be a sequence")

    observed_phase_ids: set[str] = set()
    for phase_value in phases:
        phase = _mapping(phase_value, "phase")
        phase_id = str(phase.get("phase_id", "")).strip()
        if not phase_id or phase_id in observed_phase_ids:
            raise ValueError("phase_id values must be present and unique")
        observed_phase_ids.add(phase_id)

        method = str(phase.get("discovery_method", "")).strip()
        if method not in SUPPORTED_METHODS:
            raise ValueError(f"Unsupported discovery method: {method}")
        phase_markets_value = phase.get("markets")
        phase_markets = (
            profile_markets
            if phase_markets_value == "all"
            else _unique_strings(phase_markets_value, f"{phase_id} markets")
        )
        if not set(phase_markets).issubset(profile_markets):
            raise ValueError(f"{phase_id} contains markets outside the profile")

        keywords: list[str] = []
        if method == "google_maps_standard":
            keywords = _unique_strings(phase.get("keywords"), f"{phase_id} keywords")
            if any("+" in keyword for keyword in keywords):
                raise ValueError("Keyword combinations are not allowed in the new plan")
            depth = _positive_int(phase.get("depth", 100), f"{phase_id} depth")
            pages_per_task = (depth + 99) // 100
            task_count_per_market = len(keywords)
            minimum_cost_per_market = task_count_per_market * pages_per_task * maps_price
            maximum_cost_per_market = minimum_cost_per_market
        else:
            task_count_per_market = _positive_int(
                phase.get("request_count_per_market"),
                f"{phase_id} request_count_per_market",
            )
            maximum_items = _positive_int(
                phase.get("maximum_items_per_request"),
                f"{phase_id} maximum_items_per_request",
            )
            configured_maximum = _positive_int(
                pricing["business_listings_maximum_items_per_request"],
                "business listings maximum items",
            )
            if maximum_items > configured_maximum:
                raise ValueError("Business Listings item cap exceeds configured maximum")
            minimum_cost_per_market = task_count_per_market * listing_request_price
            maximum_cost_per_market = task_count_per_market * (
                listing_request_price + maximum_items * listing_item_price
            )

        for market in phase_markets:
            region = _mapping(regions[market], f"region {market}")
            rows.append(
                {
                    "profile": profile_name,
                    "phase_id": phase_id,
                    "phase_status": str(phase.get("status", "")),
                    "market": market,
                    "state": str(region.get("state", "")),
                    "market_size": str(region.get("size", "")),
                    "discovery_method": method,
                    "planned_tasks": task_count_per_market,
                    "keywords": "|".join(keywords),
                    "estimated_minimum_cost_usd": round(minimum_cost_per_market, 6),
                    "estimated_maximum_cost_usd": round(maximum_cost_per_market, 6),
                    "condition": str(phase.get("condition", "")).strip(),
                }
            )

    plan = pd.DataFrame.from_records(rows)
    legacy = _mapping(profile.get("legacy_reference"), "legacy_reference")
    legacy_combinations = _positive_int(
        legacy.get("keyword_combination_count_per_market"),
        "legacy keyword combination count",
    )
    legacy_depth = _positive_int(legacy.get("depth", 100), "legacy depth")
    legacy_interfaces = _unique_strings(
        legacy.get("interfaces"), "legacy interfaces"
    )
    if set(legacy_interfaces) != {
        "google_maps_standard",
        "google_local_finder_standard",
    }:
        raise ValueError("Legacy reference must retain Maps and Local Finder")
    maps_pages = (legacy_depth + 99) // 100
    finder_pages = (legacy_depth + 19) // 20
    legacy_tasks_per_market = legacy_combinations * len(legacy_interfaces)
    legacy_cost_per_market = legacy_combinations * (
        maps_pages * maps_price + finder_pages * finder_page_price
    )

    phase_summary: dict[str, dict[str, Any]] = {}
    for phase_id, group in plan.groupby("phase_id", sort=False):
        phase_summary[str(phase_id)] = {
            "status": str(group["phase_status"].iloc[0]),
            "market_count": int(group["market"].nunique()),
            "planned_tasks": int(group["planned_tasks"].sum()),
            "estimated_minimum_cost_usd": round(
                float(group["estimated_minimum_cost_usd"].sum()), 4
            ),
            "estimated_maximum_cost_usd": round(
                float(group["estimated_maximum_cost_usd"].sum()), 4
            ),
        }

    summary = {
        "profile": profile_name,
        "planning_only": True,
        "execution_enabled": False,
        "api_credentials_read": False,
        "api_requests_submitted": 0,
        "market_count": len(profile_markets),
        "markets": profile_markets,
        "pricing_verified_on": str(pricing.get("verified_on", "")),
        "legacy_reference": {
            "keyword_combinations_per_market": legacy_combinations,
            "interfaces_per_market": len(legacy_interfaces),
            "tasks_per_market": legacy_tasks_per_market,
            "total_tasks": legacy_tasks_per_market * len(profile_markets),
            "estimated_total_cost_usd": round(
                legacy_cost_per_market * len(profile_markets), 4
            ),
        },
        "proposed_phases": phase_summary,
        "decision": (
            "Validate Business Listings in Malone and Syracuse before approving "
            "a 15-market rollout or any keyword supplement."
        ),
        "blocking_items": [
            "business_listings_client_and_parser",
            "exact_paid_confirmation_gate",
            "four_request_pilot_review",
        ],
    }
    return plan, summary
