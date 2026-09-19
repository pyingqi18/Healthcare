"""Plan a non-executing Business Listings validation pilot."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import asin, cos, radians, sin, sqrt
from typing import Any

import pandas as pd


EARTH_RADIUS_KM = 6371.0088


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _unique_strings(value: object, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{label} must be a sequence")
    parsed = [str(item).strip() for item in value]
    if not parsed or any(not item for item in parsed):
        raise ValueError(f"{label} cannot be empty")
    if len(parsed) != len(set(parsed)):
        raise ValueError(f"{label} contains duplicates")
    return parsed


def validate_official_categories(
    category_catalog: pd.DataFrame,
    requested_categories: Sequence[str],
) -> list[str]:
    """Return requested categories after exact official-catalog validation."""

    if "category_name" not in category_catalog.columns:
        raise KeyError("Category catalog requires category_name")
    official = category_catalog["category_name"].astype("string").str.strip()
    if official.isna().any() or official.eq("").any():
        raise ValueError("Category catalog contains blank category_name values")
    if official.duplicated().any():
        raise ValueError("Category catalog contains duplicate category_name values")
    requested = _unique_strings(requested_categories, "requested categories")
    missing = sorted(set(requested) - set(official.astype(str)))
    if missing:
        raise ValueError(f"Requested categories absent from official catalog: {missing}")
    return requested


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


def build_reference_coverage_audit(
    clinics: pd.DataFrame,
    regions_config: Mapping[str, Any],
    pilot_config: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Check whether proposed pilot circles contain corrected reference clinics."""

    required = {"clinic_key", "search_location", "latitude", "longitude"}
    missing = required - set(clinics.columns)
    if missing:
        raise KeyError(f"Clinics are missing columns: {sorted(missing)}")
    regions = _mapping(regions_config.get("regions"), "regions")
    pilot_markets = _mapping(pilot_config.get("markets"), "pilot markets")
    prefix = str(pilot_config.get("reference_key_prefix", "")).strip()
    if not prefix:
        raise ValueError("reference_key_prefix cannot be blank")

    reference = clinics[
        clinics["clinic_key"].astype("string").str.startswith(prefix, na=False)
        & clinics["search_location"].isin(pilot_markets)
    ].copy()
    if reference.empty:
        raise ValueError("No corrected pilot reference clinics were found")
    if reference["clinic_key"].duplicated().any():
        raise ValueError("Reference clinics contain duplicate clinic_key values")
    reference["latitude"] = pd.to_numeric(reference["latitude"], errors="coerce")
    reference["longitude"] = pd.to_numeric(reference["longitude"], errors="coerce")
    if reference[["latitude", "longitude"]].isna().any().any():
        raise ValueError("Reference clinics contain missing or invalid coordinates")

    distances: list[float] = []
    radii: list[float] = []
    for row in reference.itertuples(index=False):
        region = _mapping(regions.get(row.search_location), row.search_location)
        hub = region.get("hub")
        if not isinstance(hub, Sequence) or len(hub) != 2:
            raise ValueError(f"{row.search_location} requires a two-value hub")
        market_config = _mapping(
            pilot_markets[row.search_location], row.search_location
        )
        radius = float(market_config.get("radius_km", 0))
        if radius < 1:
            raise ValueError("Business Listings radius must be at least 1 km")
        distances.append(
            _distance_km(
                float(hub[0]),
                float(hub[1]),
                float(row.latitude),
                float(row.longitude),
            )
        )
        radii.append(radius)

    reference["distance_from_hub_km"] = distances
    reference["pilot_radius_km"] = radii
    reference["inside_pilot_radius"] = (
        reference["distance_from_hub_km"] <= reference["pilot_radius_km"]
    )
    reference = reference[
        [
            "clinic_key",
            "search_location",
            "latitude",
            "longitude",
            "distance_from_hub_km",
            "pilot_radius_km",
            "inside_pilot_radius",
        ]
    ].sort_values(["search_location", "clinic_key"], ignore_index=True)

    by_market: dict[str, dict[str, Any]] = {}
    for market, group in reference.groupby("search_location", sort=True):
        by_market[str(market)] = {
            "reference_clinics": len(group),
            "inside_radius": int(group["inside_pilot_radius"].sum()),
            "outside_radius": int((~group["inside_pilot_radius"]).sum()),
            "maximum_reference_distance_km": round(
                float(group["distance_from_hub_km"].max()), 4
            ),
            "pilot_radius_km": float(group["pilot_radius_km"].iloc[0]),
        }
    summary = {
        "reference_clinics": len(reference),
        "inside_radius": int(reference["inside_pilot_radius"].sum()),
        "outside_radius": int((~reference["inside_pilot_radius"]).sum()),
        "all_reference_clinics_inside_radius": bool(
            reference["inside_pilot_radius"].all()
        ),
        "by_market": by_market,
    }
    return reference, summary


def build_business_listings_pilot_manifest(
    plan_config: Mapping[str, Any],
    regions_config: Mapping[str, Any],
    category_catalog: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Create a four-request pilot manifest that cannot be submitted."""

    pilot = _mapping(plan_config.get("business_listings_pilot"), "pilot")
    if pilot.get("planning_only") is not True:
        raise ValueError("Pilot must set planning_only: true")
    if pilot.get("execution_enabled") is not False:
        raise ValueError("Pilot must set execution_enabled: false")
    requested = validate_official_categories(
        category_catalog,
        pilot.get("requested_categories", []),
    )
    maximum_categories = int(pilot.get("maximum_categories_per_request", 0))
    if not 1 <= maximum_categories <= 10:
        raise ValueError("maximum_categories_per_request must be between 1 and 10")
    category_groups = [
        requested[index : index + maximum_categories]
        for index in range(0, len(requested), maximum_categories)
    ]

    regions = _mapping(regions_config.get("regions"), "regions")
    pilot_markets = _mapping(pilot.get("markets"), "pilot markets")
    pricing = _mapping(plan_config.get("pricing"), "pricing")
    request_cost = float(pricing["business_listings_live_per_request"])
    item_cost = float(pricing["business_listings_live_per_item"])
    maximum_items = int(pricing["business_listings_maximum_items_per_request"])

    rows: list[dict[str, Any]] = []
    for market, market_value in pilot_markets.items():
        region = _mapping(regions.get(market), str(market))
        hub = region.get("hub")
        if not isinstance(hub, Sequence) or len(hub) != 2:
            raise ValueError(f"{market} requires a two-value hub")
        market_config = _mapping(market_value, str(market))
        radius = float(market_config.get("radius_km", 0))
        if radius < 1:
            raise ValueError("Business Listings radius must be at least 1 km")
        coordinate = f"{float(hub[0]):.7f},{float(hub[1]):.7f},{radius:g}"
        for group_number, categories in enumerate(category_groups, start=1):
            rows.append(
                {
                    "task_tag": f"business_listings_pilot:{market}:g{group_number:02d}",
                    "market": str(market),
                    "category_group": group_number,
                    "categories": "|".join(categories),
                    "category_count": len(categories),
                    "location_coordinate": coordinate,
                    "limit": maximum_items,
                    "estimated_minimum_cost_usd": round(request_cost, 6),
                    "estimated_maximum_cost_usd": round(
                        request_cost + maximum_items * item_cost, 6
                    ),
                    "planning_only": True,
                    "execution_enabled": False,
                }
            )
    manifest = pd.DataFrame.from_records(rows)
    if not manifest["task_tag"].is_unique:
        raise ValueError("Pilot task_tag values are not unique")

    gate = _mapping(pilot.get("recall_gate"), "recall_gate")
    gate_values = {key: float(value) for key, value in gate.items()}
    if any(value < 0 or value > 1 for value in gate_values.values()):
        raise ValueError("Recall thresholds must be between zero and one")
    summary = {
        "planning_only": True,
        "execution_enabled": False,
        "api_requests_submitted": 0,
        "market_count": int(manifest["market"].nunique()),
        "requested_category_count": len(requested),
        "category_groups_per_market": len(category_groups),
        "planned_requests": len(manifest),
        "estimated_minimum_cost_usd": round(
            float(manifest["estimated_minimum_cost_usd"].sum()), 4
        ),
        "estimated_maximum_cost_usd": round(
            float(manifest["estimated_maximum_cost_usd"].sum()), 4
        ),
        "recall_gate": gate_values,
        "decision_rule": {
            "approve_as_primary": (
                "overall recall >= 0.95 and every market recall >= 0.90"
            ),
            "add_maps_supplement": (
                "overall recall >= 0.90 but primary approval gate is not met"
            ),
            "reject_or_redesign": (
                "overall recall < 0.90 or any market recall < 0.80"
            ),
        },
    }
    return manifest, summary


def evaluate_pilot_recall(
    matches: pd.DataFrame,
    recall_gate: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Classify pilot recall without treating the legacy reference as truth."""

    required = {"reference_key", "market", "discovered"}
    missing = required - set(matches.columns)
    if missing:
        raise KeyError(f"Recall matches are missing columns: {sorted(missing)}")
    if matches.empty:
        raise ValueError("Recall matches cannot be empty")
    if matches["reference_key"].isna().any():
        raise ValueError("Recall matches contain missing reference_key values")
    if matches["reference_key"].duplicated().any():
        raise ValueError("Recall matches contain duplicate reference_key values")
    discovered = matches["discovered"]
    if not discovered.map(lambda value: isinstance(value, bool)).all():
        raise TypeError("discovered must contain boolean values")

    gate = {key: float(value) for key, value in recall_gate.items()}
    required_gate = {
        "approve_primary_overall_minimum",
        "approve_primary_each_market_minimum",
        "supplement_overall_minimum",
        "reject_each_market_below",
    }
    missing_gate = required_gate - set(gate)
    if missing_gate:
        raise KeyError(f"Recall gate is missing values: {sorted(missing_gate)}")
    if any(value < 0 or value > 1 for value in gate.values()):
        raise ValueError("Recall thresholds must be between zero and one")

    records: list[dict[str, Any]] = []
    for market, group in matches.groupby("market", sort=True):
        records.append(
            {
                "market": str(market),
                "reference_count": len(group),
                "discovered_count": int(group["discovered"].sum()),
                "recall": float(group["discovered"].mean()),
            }
        )
    market_summary = pd.DataFrame.from_records(records)
    overall_recall = float(matches["discovered"].mean())
    minimum_market_recall = float(market_summary["recall"].min())

    if (
        overall_recall < gate["supplement_overall_minimum"]
        or minimum_market_recall < gate["reject_each_market_below"]
    ):
        decision = "reject_or_redesign"
    elif (
        overall_recall >= gate["approve_primary_overall_minimum"]
        and minimum_market_recall
        >= gate["approve_primary_each_market_minimum"]
    ):
        decision = "approve_as_primary"
    else:
        decision = "maps_supplement_required"

    summary = {
        "reference_count": len(matches),
        "discovered_count": int(matches["discovered"].sum()),
        "overall_recall": overall_recall,
        "minimum_market_recall": minimum_market_recall,
        "decision": decision,
        "interpretation_limit": (
            "Recall is measured against the corrected legacy reference set; "
            "newly discovered valid clinics are audited separately."
        ),
    }
    return market_summary, summary
