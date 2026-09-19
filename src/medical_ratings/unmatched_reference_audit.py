"""Build an evidence-based review queue for references missed by both sources."""

from __future__ import annotations

from typing import Any

import pandas as pd


MATCH_DETAIL_COLUMNS = [
    "coordinate_only_review_candidate_count",
    "best_candidate_key",
    "best_candidate_cid",
    "best_candidate_title",
    "best_candidate_category",
    "best_candidate_status",
    "best_candidate_address",
    "best_distance_meters",
    "best_same_address",
    "best_same_phone",
    "best_title_similarity",
    "best_matching_evidence",
]


def _match_details(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    required = {"market", "reference_key", "discovered"}
    missing = required - set(frame.columns)
    if missing:
        raise KeyError(f"{prefix} matches are missing: {sorted(missing)}")
    if frame.duplicated(["market", "reference_key"]).any():
        raise ValueError(f"{prefix} matches contain duplicate reference keys")
    available = [column for column in MATCH_DETAIL_COLUMNS if column in frame.columns]
    selected = frame[["market", "reference_key", *available]].copy()
    return selected.rename(
        columns={column: f"{prefix}_{column}" for column in available}
    )


def build_unmatched_reference_review(
    source_union: pd.DataFrame,
    reference_universe: pd.DataFrame,
    business_matches: pd.DataFrame,
    maps_matches: pd.DataFrame,
    market_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Attach reference identity and nearest-candidate evidence to unmatched units."""

    union_required = {"market", "reference_key", "source_discovery_status"}
    missing_union = union_required - set(source_union.columns)
    if missing_union:
        raise KeyError(f"Source union is missing: {sorted(missing_union)}")
    unmatched = source_union.loc[
        source_union["source_discovery_status"].eq("not_discovered_by_either"),
        ["market", "reference_key"],
    ].copy()
    if unmatched.empty:
        raise ValueError("No references are unmatched by both sources")

    universe_required = {
        "search_location",
        "clinic_key",
        "title",
        "address",
        "zip",
        "latitude",
        "longitude",
        "phone",
        "domain",
        "reference_geography_status",
    }
    missing_universe = universe_required - set(reference_universe.columns)
    if missing_universe:
        raise KeyError(f"Reference universe is missing: {sorted(missing_universe)}")
    universe = reference_universe.loc[
        reference_universe["reference_geography_status"].eq("eligible_target_zip"),
        list(universe_required),
    ].copy()
    universe = universe.rename(
        columns={
            "search_location": "market",
            "clinic_key": "reference_key",
            "title": "reference_title",
            "address": "reference_address",
            "zip": "reference_zip",
            "latitude": "reference_latitude",
            "longitude": "reference_longitude",
            "phone": "reference_phone",
            "domain": "reference_domain",
        }
    )
    if universe.duplicated(["market", "reference_key"]).any():
        raise ValueError("Reference universe contains duplicate eligible keys")

    summary_required = {"market", "remaining_unmatched_units", "benchmark_decision"}
    missing_summary = summary_required - set(market_summary.columns)
    if missing_summary:
        raise KeyError(f"Market summary is missing: {sorted(missing_summary)}")
    decision = market_summary[list(summary_required)].copy()
    if decision["market"].duplicated().any():
        raise ValueError("Market summary contains duplicate markets")

    review = unmatched.merge(
        universe,
        on=["market", "reference_key"],
        how="left",
        validate="one_to_one",
    )
    if review["reference_title"].isna().all():
        raise ValueError("Unmatched references did not join to the reference universe")
    review = review.merge(
        _match_details(business_matches, "business_listings"),
        on=["market", "reference_key"],
        how="left",
        validate="one_to_one",
    )
    review = review.merge(
        _match_details(maps_matches, "maps_standard"),
        on=["market", "reference_key"],
        how="left",
        validate="one_to_one",
    )
    review = review.merge(
        decision,
        on="market",
        how="left",
        validate="many_to_one",
    )
    if review["benchmark_decision"].isna().any():
        raise ValueError("Some unmatched references lack a market decision")
    actual_counts = review.groupby("market").size()
    expected_counts = decision.set_index("market")["remaining_unmatched_units"]
    for market, actual in actual_counts.items():
        if int(actual) != int(expected_counts.loc[market]):
            raise ValueError(f"Unmatched count differs from market summary: {market}")

    distances = []
    for column in [
        "business_listings_best_distance_meters",
        "maps_standard_best_distance_meters",
    ]:
        if column in review:
            distances.append(pd.to_numeric(review[column], errors="coerce"))
    if distances:
        review["nearest_candidate_distance_meters"] = pd.concat(
            distances, axis=1
        ).min(axis=1, skipna=True)
    else:
        review["nearest_candidate_distance_meters"] = pd.NA
    coordinate_review_columns = [
        column
        for column in [
            "business_listings_coordinate_only_review_candidate_count",
            "maps_standard_coordinate_only_review_candidate_count",
        ]
        if column in review
    ]
    if coordinate_review_columns:
        coordinate_review_count = (
            review[coordinate_review_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0)
            .sum(axis=1)
        )
    else:
        coordinate_review_count = pd.Series(0, index=review.index)
    review["coordinate_only_review_candidate_count"] = coordinate_review_count.astype(int)

    latitude = pd.to_numeric(review["reference_latitude"], errors="coerce")
    longitude = pd.to_numeric(review["reference_longitude"], errors="coerce")
    valid_coordinates = latitude.between(-90, 90) & longitude.between(-180, 180)
    normalized_address = review["reference_address"].astype("string").str.strip()
    address_present = normalized_address.notna() & normalized_address.ne("")
    insufficient = ~valid_coordinates & ~address_present
    close = (
        review["coordinate_only_review_candidate_count"].gt(0)
        | review["nearest_candidate_distance_meters"].le(100).fillna(False)
    )
    nearby = review["nearest_candidate_distance_meters"].le(500).fillna(False)
    review["review_tier"] = "targeted_current_status_review"
    review.loc[nearby, "review_tier"] = "nearby_identity_review"
    review.loc[close, "review_tier"] = "close_identity_review"
    review.loc[insufficient, "review_tier"] = "insufficient_reference_identity"

    action_map = {
        "close_identity_review": "compare title, address, phone, and profile identity before treating this as missed",
        "nearby_identity_review": "inspect nearby candidates for relocation, rename, or weak identity evidence",
        "targeted_current_status_review": "check current status and exact historical title or address before paid search",
        "insufficient_reference_identity": "repair historical address or coordinates before any coverage conclusion",
    }
    review["recommended_review_action"] = review["review_tier"].map(action_map)
    high_market = review["benchmark_decision"].eq("discovery_redesign_required")
    high_tier = review["review_tier"].isin(
        {"close_identity_review", "insufficient_reference_identity"}
    )
    review["review_priority"] = "standard"
    review.loc[high_market | high_tier, "review_priority"] = "high"
    review["manual_decision"] = ""
    review["manual_evidence"] = ""
    review["reviewed_by"] = ""
    review["reviewed_on"] = ""
    return review.sort_values(
        ["review_priority", "review_tier", "market", "reference_key"],
        ascending=[True, True, True, True],
        ignore_index=True,
    )


def summarize_unmatched_reference_review(
    review: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Summarize the queue without making automatic historical-status decisions."""

    rows: list[dict[str, Any]] = []
    for market, group in review.groupby("market", sort=True):
        rows.append(
            {
                "market": market,
                "benchmark_decision": group["benchmark_decision"].iloc[0],
                "unmatched_reference_units": len(group),
                "close_identity_review": int(group["review_tier"].eq("close_identity_review").sum()),
                "nearby_identity_review": int(group["review_tier"].eq("nearby_identity_review").sum()),
                "targeted_current_status_review": int(group["review_tier"].eq("targeted_current_status_review").sum()),
                "insufficient_reference_identity": int(group["review_tier"].eq("insufficient_reference_identity").sum()),
                "high_priority": int(group["review_priority"].eq("high").sum()),
            }
        )
    by_market = pd.DataFrame.from_records(rows)
    summary = {
        "analysis_status": "all_market_unmatched_reference_review_queue_not_final",
        "api_requests_submitted": 0,
        "unmatched_reference_units": len(review),
        "markets_with_unmatched_references": int(review["market"].nunique()),
        "review_tiers": {
            str(key): int(value)
            for key, value in review["review_tier"].value_counts().items()
        },
        "review_priorities": {
            str(key): int(value)
            for key, value in review["review_priority"].value_counts().items()
        },
        "automatic_current_status_decisions": 0,
        "automatic_paid_follow_up": False,
        "automatic_profile_or_location_merges": 0,
        "next_required_action": "Review identity and current-status evidence before planning any paid gap search.",
    }
    return by_market, summary
