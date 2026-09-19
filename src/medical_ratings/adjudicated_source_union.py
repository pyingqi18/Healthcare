"""Apply reviewed identity decisions to the frozen all-market source union."""

from __future__ import annotations

from typing import Any

import pandas as pd

from medical_ratings.source_union_audit import summarize_reference_source_union


REQUIRED_UNION_COLUMNS = {
    "market",
    "reference_key",
    "business_listings_discovered",
    "maps_standard_discovered",
    "source_union_discovered",
    "source_discovery_status",
}
REQUIRED_REVIEW_COLUMNS = {
    "market",
    "reference_key",
    "proposed_decision",
    "confirmed_identity_match",
    "exclude_from_current_reference_denominator",
    "business_listings_candidate_rule_match",
    "maps_standard_candidate_rule_match",
}


def _boolean(values: pd.Series, label: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False)
    normalized = values.astype("string").str.strip().str.casefold()
    invalid = set(normalized.dropna()) - {"true", "false", "1", "0"}
    if invalid:
        raise ValueError(f"{label} contains invalid booleans: {sorted(invalid)}")
    return normalized.isin({"true", "1"})


def _set_source_status(frame: pd.DataFrame) -> None:
    business = frame["business_listings_discovered"]
    maps = frame["maps_standard_discovered"]
    frame["source_union_discovered"] = business | maps
    frame["source_discovery_status"] = "not_discovered_by_either"
    frame.loc[business & ~maps, "source_discovery_status"] = "business_only"
    frame.loc[~business & maps, "source_discovery_status"] = "maps_incremental"
    frame.loc[business & maps, "source_discovery_status"] = "discovered_by_both"


def apply_adjudication_to_source_union(
    source_union: pd.DataFrame,
    reviewed_candidates: pd.DataFrame,
    *,
    expected_markets: set[str],
    primary_market_minimum: float,
    reject_market_below: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Adjust exact reviewed keys and recalculate the current-reference recall."""

    missing_union = REQUIRED_UNION_COLUMNS - set(source_union.columns)
    if missing_union:
        raise KeyError(f"Source union is missing: {sorted(missing_union)}")
    missing_review = REQUIRED_REVIEW_COLUMNS - set(reviewed_candidates.columns)
    if missing_review:
        raise KeyError(f"Reviewed candidates are missing: {sorted(missing_review)}")
    if source_union.duplicated(["market", "reference_key"]).any():
        raise ValueError("Source union contains duplicate market-reference keys")
    if reviewed_candidates.duplicated(["market", "reference_key"]).any():
        raise ValueError("Reviewed candidates contain duplicate market-reference keys")

    adjusted = source_union.copy()
    reviewed = reviewed_candidates.copy()
    for frame in (adjusted, reviewed):
        frame["market"] = frame["market"].astype("string").str.strip()
        frame["reference_key"] = frame["reference_key"].astype("string").str.strip()
    expected = {str(value).strip() for value in expected_markets}
    if set(adjusted["market"].dropna()) != expected:
        raise ValueError("Source union markets differ from the frozen market set")

    for column in (
        "business_listings_discovered",
        "maps_standard_discovered",
        "source_union_discovered",
    ):
        adjusted[column] = _boolean(adjusted[column], column)
    original = adjusted.copy()
    for column in (
        "confirmed_identity_match",
        "exclude_from_current_reference_denominator",
        "business_listings_candidate_rule_match",
        "maps_standard_candidate_rule_match",
    ):
        reviewed[column] = _boolean(reviewed[column], column)

    union_keys = set(zip(adjusted["market"], adjusted["reference_key"]))
    review_keys = set(zip(reviewed["market"], reviewed["reference_key"]))
    missing_keys = sorted(review_keys - union_keys)[:5]
    if missing_keys:
        raise ValueError(f"Reviewed references are absent from source union: {missing_keys}")
    joined_status = reviewed.merge(
        adjusted[["market", "reference_key", "source_union_discovered"]],
        on=["market", "reference_key"],
        how="left",
        validate="one_to_one",
    )
    if joined_status["source_union_discovered"].any():
        raise ValueError("Reviewed candidate was already discovered before adjudication")
    conflicting = reviewed["confirmed_identity_match"] & reviewed[
        "exclude_from_current_reference_denominator"
    ]
    if conflicting.any():
        raise ValueError("A reference cannot be both matched and denominator-excluded")
    confirmed = reviewed["confirmed_identity_match"]
    confirmed_source = (
        reviewed["business_listings_candidate_rule_match"]
        | reviewed["maps_standard_candidate_rule_match"]
    )
    if (confirmed & ~confirmed_source).any():
        raise ValueError("Confirmed identity match lacks a reviewed source match")

    adjusted["original_source_discovery_status"] = adjusted[
        "source_discovery_status"
    ]
    adjusted["current_reference_included"] = True
    adjusted["manual_identity_adjudication_applied"] = False
    adjusted["manual_identity_decision"] = ""
    review_lookup = reviewed.set_index(["market", "reference_key"])
    adjusted_index = adjusted.set_index(["market", "reference_key"])
    for key, decision in review_lookup.iterrows():
        adjusted_index.loc[key, "manual_identity_adjudication_applied"] = True
        adjusted_index.loc[key, "manual_identity_decision"] = decision[
            "proposed_decision"
        ]
        if bool(decision["exclude_from_current_reference_denominator"]):
            adjusted_index.loc[key, "current_reference_included"] = False
        if bool(decision["confirmed_identity_match"]):
            if bool(decision["business_listings_candidate_rule_match"]):
                adjusted_index.loc[key, "business_listings_discovered"] = True
            if bool(decision["maps_standard_candidate_rule_match"]):
                adjusted_index.loc[key, "maps_standard_discovered"] = True
    adjusted = adjusted_index.reset_index()
    for column in (
        "business_listings_discovered",
        "maps_standard_discovered",
        "current_reference_included",
        "manual_identity_adjudication_applied",
    ):
        adjusted[column] = adjusted[column].astype(bool)
    _set_source_status(adjusted)

    original_by_market, original_summary = summarize_reference_source_union(
        original,
        expected_markets=expected,
        primary_market_minimum=primary_market_minimum,
        reject_market_below=reject_market_below,
    )
    eligible = adjusted.loc[adjusted["current_reference_included"]].copy()
    by_market, summary = summarize_reference_source_union(
        eligible,
        expected_markets=expected,
        primary_market_minimum=primary_market_minimum,
        reject_market_below=reject_market_below,
    )
    review_counts = (
        reviewed.groupby("market", as_index=False)
        .agg(
            manually_confirmed_matches_added=("confirmed_identity_match", "sum"),
            reference_denominator_exclusions=(
                "exclude_from_current_reference_denominator",
                "sum",
            ),
        )
    )
    original_columns = original_by_market[
        [
            "market",
            "fused_historical_target_zip_units",
            "source_union_discovered_units",
            "source_union_recall",
            "benchmark_decision",
        ]
    ].rename(
        columns={
            "fused_historical_target_zip_units": "original_reference_units",
            "source_union_discovered_units": "original_source_union_discovered_units",
            "source_union_recall": "original_source_union_recall",
            "benchmark_decision": "original_benchmark_decision",
        }
    )
    by_market = by_market.merge(
        original_columns, on="market", how="left", validate="one_to_one"
    ).merge(review_counts, on="market", how="left", validate="one_to_one")
    for column in (
        "manually_confirmed_matches_added",
        "reference_denominator_exclusions",
    ):
        by_market[column] = by_market[column].fillna(0).astype(int)
    by_market["source_union_recall_change"] = (
        by_market["source_union_recall"]
        - by_market["original_source_union_recall"]
    )
    changed_gate = by_market["benchmark_decision"].ne(
        by_market["original_benchmark_decision"]
    )
    summary.update(
        {
            "analysis_status": "all_15_markets_source_union_after_manual_identity_adjudication",
            "original_fused_historical_target_zip_units": original_summary[
                "fused_historical_target_zip_units"
            ],
            "reference_denominator_exclusions": int(
                reviewed["exclude_from_current_reference_denominator"].sum()
            ),
            "adjusted_current_reference_units": len(eligible),
            "original_source_union_discovered_units": original_summary[
                "source_union_discovered_units"
            ],
            "manually_confirmed_matches_added": int(
                reviewed["confirmed_identity_match"].sum()
            ),
            "adjusted_source_union_discovered_units": int(
                eligible["source_union_discovered"].sum()
            ),
            "original_source_union_recall": original_summary["source_union_recall"],
            "adjusted_source_union_recall": int(
                eligible["source_union_discovered"].sum()
            )
            / len(eligible),
            "source_union_recall_change": (
                int(eligible["source_union_discovered"].sum()) / len(eligible)
                - original_summary["source_union_recall"]
            ),
            "remaining_unmatched_current_references": int(
                (~eligible["source_union_discovered"]).sum()
            ),
            "markets_with_benchmark_decision_change": by_market.loc[
                changed_gate, "market"
            ].tolist(),
            "automatic_paid_follow_up": False,
            "automatic_profile_or_location_merges": 0,
        }
    )
    return (
        adjusted.sort_values(["market", "reference_key"], ignore_index=True),
        by_market.sort_values("market", ignore_index=True),
        summary,
    )
