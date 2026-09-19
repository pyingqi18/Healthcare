"""Measure source union recall on the same historical competition units."""

from __future__ import annotations

from typing import Any

import pandas as pd


REQUIRED_MATCH_COLUMNS = {"reference_key", "market", "discovered"}


def _boolean(values: pd.Series, label: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False)
    normalized = values.astype("string").str.strip().str.casefold()
    invalid = set(normalized.dropna()) - {"true", "false", "1", "0"}
    if invalid:
        raise ValueError(f"{label} contains invalid booleans: {sorted(invalid)}")
    return normalized.isin({"true", "1"})


def build_reference_source_union(
    business_matches: pd.DataFrame,
    maps_matches: pd.DataFrame,
    *,
    expected_markets: set[str],
) -> pd.DataFrame:
    """Join source discoveries one-to-one on frozen historical location keys."""

    prepared: dict[str, pd.DataFrame] = {}
    expected = {str(value).strip() for value in expected_markets}
    for label, frame in [
        ("business_listings", business_matches),
        ("maps_standard", maps_matches),
    ]:
        missing = REQUIRED_MATCH_COLUMNS - set(frame.columns)
        if missing:
            raise KeyError(f"{label} matches are missing: {sorted(missing)}")
        if frame.duplicated(["market", "reference_key"]).any():
            raise ValueError(f"{label} contains duplicate market-reference keys")
        actual = set(frame["market"].dropna().astype(str))
        if actual != expected:
            raise ValueError(f"{label} markets differ from the frozen market set")
        selected_columns = ["market", "reference_key", "discovered"]
        optional = [
            "best_candidate_key",
            "best_candidate_cid",
            "best_candidate_title",
            "best_candidate_status",
            "best_matching_evidence",
            "best_distance_meters",
        ]
        selected_columns.extend(column for column in optional if column in frame.columns)
        selected = frame[selected_columns].copy()
        selected["discovered"] = _boolean(selected["discovered"], label)
        selected = selected.rename(
            columns={
                column: f"{label}_{column}"
                for column in selected.columns
                if column not in {"market", "reference_key"}
            }
        )
        prepared[label] = selected

    union = prepared["business_listings"].merge(
        prepared["maps_standard"],
        on=["market", "reference_key"],
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    if not union["_merge"].eq("both").all():
        raise ValueError("Business Listings and Maps use different reference universes")
    union = union.drop(columns="_merge")
    business = union["business_listings_discovered"]
    maps = union["maps_standard_discovered"]
    union["source_union_discovered"] = business | maps
    union["source_discovery_status"] = "not_discovered_by_either"
    union.loc[business & ~maps, "source_discovery_status"] = "business_only"
    union.loc[~business & maps, "source_discovery_status"] = "maps_incremental"
    union.loc[business & maps, "source_discovery_status"] = "discovered_by_both"
    return union.sort_values(["market", "reference_key"], ignore_index=True)


def summarize_reference_source_union(
    union: pd.DataFrame,
    *,
    expected_markets: set[str],
    primary_market_minimum: float,
    reject_market_below: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Summarize marginal Maps recovery and remaining gaps by market."""

    if not 0 <= reject_market_below <= primary_market_minimum <= 1:
        raise ValueError("Recall thresholds must satisfy 0 <= reject <= primary <= 1")
    required = {
        "market",
        "reference_key",
        "business_listings_discovered",
        "maps_standard_discovered",
        "source_union_discovered",
        "source_discovery_status",
    }
    missing = required - set(union.columns)
    if missing:
        raise KeyError(f"Source union is missing: {sorted(missing)}")

    rows: list[dict[str, Any]] = []
    for market in sorted(expected_markets):
        group = union.loc[union["market"].eq(market)]
        if group.empty:
            raise ValueError(f"No reference locations for market: {market}")
        reference_count = len(group)
        business_count = int(group["business_listings_discovered"].sum())
        maps_count = int(group["maps_standard_discovered"].sum())
        both_count = int(group["source_discovery_status"].eq("discovered_by_both").sum())
        maps_incremental = int(group["source_discovery_status"].eq("maps_incremental").sum())
        union_count = int(group["source_union_discovered"].sum())
        remaining = reference_count - union_count
        union_recall = union_count / reference_count
        if union_recall >= primary_market_minimum:
            decision = "meets_primary_market_gate"
        elif union_recall < reject_market_below:
            decision = "discovery_redesign_required"
        else:
            decision = "targeted_gap_audit_required"
        rows.append(
            {
                "market": market,
                "fused_historical_target_zip_units": reference_count,
                "business_listings_discovered_units": business_count,
                "business_listings_recall": business_count / reference_count,
                "maps_standard_discovered_units": maps_count,
                "maps_standard_recall": maps_count / reference_count,
                "discovered_by_both_units": both_count,
                "maps_incremental_units": maps_incremental,
                "maps_incremental_share_of_reference": maps_incremental / reference_count,
                "source_union_discovered_units": union_count,
                "source_union_recall": union_recall,
                "remaining_unmatched_units": remaining,
                "benchmark_decision": decision,
            }
        )
    by_market = pd.DataFrame.from_records(rows)
    reference_total = int(by_market["fused_historical_target_zip_units"].sum())
    business_total = int(by_market["business_listings_discovered_units"].sum())
    maps_total = int(by_market["maps_standard_discovered_units"].sum())
    both_total = int(by_market["discovered_by_both_units"].sum())
    incremental_total = int(by_market["maps_incremental_units"].sum())
    union_total = int(by_market["source_union_discovered_units"].sum())
    remaining_total = int(by_market["remaining_unmatched_units"].sum())
    summary = {
        "analysis_status": "all_15_markets_reference_source_union_audit_not_final",
        "api_requests_submitted": 0,
        "market_count": len(expected_markets),
        "markets_audited": sorted(expected_markets),
        "fused_historical_target_zip_units": reference_total,
        "business_listings_discovered_units": business_total,
        "business_listings_recall": business_total / reference_total,
        "maps_standard_discovered_units": maps_total,
        "maps_standard_recall": maps_total / reference_total,
        "discovered_by_both_units": both_total,
        "maps_incremental_units": incremental_total,
        "maps_incremental_share_of_reference": incremental_total / reference_total,
        "source_union_discovered_units": union_total,
        "source_union_recall": union_total / reference_total,
        "remaining_unmatched_units": remaining_total,
        "markets_by_benchmark_decision": {
            str(key): int(value)
            for key, value in by_market["benchmark_decision"].value_counts().items()
        },
        "primary_market_minimum": primary_market_minimum,
        "reject_market_below": reject_market_below,
        "automatic_paid_follow_up": False,
        "automatic_profile_or_location_merges": 0,
        "interpretation_limits": [
            "Source union recall counts historical competition units found by either source and does not add source-specific recall rates.",
            "A historical unit not rediscovered can be closed, renamed, identity-changed, or missed; it is audited before any paid follow-up.",
            "A Maps-only Google profile is not automatically a new physical competition location.",
        ],
    }
    return by_market, summary
