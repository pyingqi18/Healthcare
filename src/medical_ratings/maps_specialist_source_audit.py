"""Audit specialist Maps profiles and extend the adjudicated source union."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


REQUIRED_EXISTING_PROFILE_COLUMNS = {
    "requested_location",
    "profile_key",
    "market_assignment_status",
}
REQUIRED_SPECIALIST_COLUMNS = REQUIRED_EXISTING_PROFILE_COLUMNS | {
    "eligibility_review_status",
}
REQUIRED_BASELINE_COLUMNS = {
    "market",
    "reference_key",
    "business_listings_discovered",
    "maps_standard_discovered",
    "source_union_discovered",
    "current_reference_included",
}
REQUIRED_MATCH_COLUMNS = {"market", "reference_key", "discovered"}


def _boolean(values: pd.Series, label: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False).astype(bool)
    normalized = values.astype("string").str.strip().str.casefold()
    invalid = set(normalized.dropna()) - {"true", "false", "1", "0"}
    if invalid:
        raise ValueError(f"{label} contains invalid booleans: {sorted(invalid)}")
    return normalized.isin({"true", "1"})


def _prepare_profile_source(
    frame: pd.DataFrame,
    *,
    source_label: str,
    expected_markets: set[str],
) -> pd.DataFrame:
    missing = REQUIRED_EXISTING_PROFILE_COLUMNS - set(frame.columns)
    if missing:
        raise KeyError(f"{source_label} is missing: {sorted(missing)}")
    selected = frame.copy()
    selected["requested_location"] = (
        selected["requested_location"].astype("string").str.strip()
    )
    selected["profile_key"] = selected["profile_key"].astype("string").str.strip()
    actual = set(selected["requested_location"].dropna().astype(str))
    if actual != expected_markets:
        raise ValueError(f"{source_label} markets differ from the frozen market set")
    if selected.duplicated(["requested_location", "profile_key"]).any():
        raise ValueError(f"{source_label} contains duplicate market-profile keys")
    eligible = selected.loc[
        selected["market_assignment_status"].eq("eligible_target_zip"),
        ["requested_location", "profile_key"],
    ].copy()
    eligible[f"seen_in_{source_label}"] = True
    return eligible


def build_existing_profile_index(
    business_listings: pd.DataFrame,
    core_maps: pd.DataFrame,
    *,
    expected_markets: set[str],
) -> pd.DataFrame:
    """Index target-ZIP Google profiles already seen by earlier source layers."""

    expected = {str(value).strip() for value in expected_markets}
    business = _prepare_profile_source(
        business_listings,
        source_label="business_listings",
        expected_markets=expected,
    )
    maps = _prepare_profile_source(
        core_maps,
        source_label="core_maps",
        expected_markets=expected,
    )
    combined = business.merge(
        maps,
        on=["requested_location", "profile_key"],
        how="outer",
        validate="one_to_one",
    )
    for column in ("seen_in_business_listings", "seen_in_core_maps"):
        combined[column] = combined[column].eq(True)
    combined["seen_in_any_existing_source"] = (
        combined["seen_in_business_listings"] | combined["seen_in_core_maps"]
    )
    return combined.sort_values(
        ["requested_location", "profile_key"], ignore_index=True
    )


def compare_specialist_profiles(
    specialist_reviewed: pd.DataFrame,
    existing_profile_index: pd.DataFrame,
    *,
    expected_markets: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Measure exact Google-profile overlap after target-ZIP review."""

    missing = REQUIRED_SPECIALIST_COLUMNS - set(specialist_reviewed.columns)
    if missing:
        raise KeyError(f"Specialist profile audit is missing: {sorted(missing)}")
    expected = {str(value).strip() for value in expected_markets}
    actual = set(
        specialist_reviewed["requested_location"].dropna().astype(str)
    )
    if actual != expected:
        raise ValueError("Specialist profiles differ from the frozen market set")
    if specialist_reviewed.duplicated(
        ["requested_location", "profile_key"]
    ).any():
        raise ValueError("Specialist profiles contain duplicate market-profile keys")

    eligible = specialist_reviewed.loc[
        specialist_reviewed["market_assignment_status"].eq("eligible_target_zip")
    ].copy()
    compared = eligible.merge(
        existing_profile_index,
        on=["requested_location", "profile_key"],
        how="left",
        validate="one_to_one",
    )
    for column in (
        "seen_in_business_listings",
        "seen_in_core_maps",
        "seen_in_any_existing_source",
    ):
        compared[column] = compared[column].eq(True)
    compared["specialist_exact_profile_status"] = "specialist_only_exact_profile"
    compared.loc[
        compared["seen_in_core_maps"] & ~compared["seen_in_business_listings"],
        "specialist_exact_profile_status",
    ] = "seen_in_core_maps_only"
    compared.loc[
        compared["seen_in_business_listings"] & ~compared["seen_in_core_maps"],
        "specialist_exact_profile_status",
    ] = "seen_in_business_listings_only"
    compared.loc[
        compared["seen_in_business_listings"] & compared["seen_in_core_maps"],
        "specialist_exact_profile_status",
    ] = "seen_in_business_listings_and_core_maps"

    rows: list[dict[str, Any]] = []
    for market in sorted(expected):
        group = compared.loc[compared["requested_location"].eq(market)]
        rows.append(
            {
                "market": market,
                "specialist_target_zip_profiles": len(group),
                "seen_in_business_listings_profiles": int(
                    group["seen_in_business_listings"].sum()
                ),
                "seen_in_core_maps_profiles": int(group["seen_in_core_maps"].sum()),
                "seen_in_any_existing_source_profiles": int(
                    group["seen_in_any_existing_source"].sum()
                ),
                "specialist_only_exact_profiles": int(
                    (~group["seen_in_any_existing_source"]).sum()
                ),
                "specialist_only_provisional_dental_profiles": int(
                    (
                        ~group["seen_in_any_existing_source"]
                        & group["eligibility_review_status"].eq(
                            "include_dental_provider"
                        )
                    ).sum()
                ),
                "specialist_only_manual_category_review_profiles": int(
                    (
                        ~group["seen_in_any_existing_source"]
                        & group["eligibility_review_status"].eq(
                            "manual_category_review"
                        )
                    ).sum()
                ),
            }
        )
    return compared.reset_index(drop=True), pd.DataFrame.from_records(rows)


def extend_adjudicated_source_union(
    adjudicated_union: pd.DataFrame,
    specialist_reference_matches: pd.DataFrame,
    specialist_profile_by_market: pd.DataFrame,
    *,
    expected_markets: set[str],
    primary_market_minimum: float,
    reject_market_below: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Add specialist discovery without changing prior manual adjudication."""

    missing_union = REQUIRED_BASELINE_COLUMNS - set(adjudicated_union.columns)
    if missing_union:
        raise KeyError(f"Adjudicated source union is missing: {sorted(missing_union)}")
    missing_matches = REQUIRED_MATCH_COLUMNS - set(specialist_reference_matches.columns)
    if missing_matches:
        raise KeyError(f"Specialist reference matches are missing: {sorted(missing_matches)}")
    if not 0 <= reject_market_below <= primary_market_minimum <= 1:
        raise ValueError("Recall gates must satisfy 0 <= reject <= primary <= 1")

    expected = {str(value).strip() for value in expected_markets}
    baseline = adjudicated_union.copy()
    matches = specialist_reference_matches.copy()
    for frame in (baseline, matches):
        frame["market"] = frame["market"].astype("string").str.strip()
        frame["reference_key"] = frame["reference_key"].astype("string").str.strip()
    if set(baseline["market"].dropna().astype(str)) != expected:
        raise ValueError("Adjudicated union markets differ from the frozen set")
    if set(matches["market"].dropna().astype(str)) != expected:
        raise ValueError("Specialist match markets differ from the frozen set")
    if baseline.duplicated(["market", "reference_key"]).any():
        raise ValueError("Adjudicated union contains duplicate reference keys")
    if matches.duplicated(["market", "reference_key"]).any():
        raise ValueError("Specialist matches contain duplicate reference keys")

    for column in (
        "business_listings_discovered",
        "maps_standard_discovered",
        "source_union_discovered",
        "current_reference_included",
    ):
        baseline[column] = _boolean(baseline[column], column)
    matches["maps_specialist_discovered"] = _boolean(
        matches["discovered"], "specialist discovered"
    )
    match_columns = [
        "market",
        "reference_key",
        "maps_specialist_discovered",
        *[
            column
            for column in (
                "discovered_with_provisional_include",
                "matched_candidate_count",
                "matched_included_candidate_count",
                "best_candidate_key",
                "best_candidate_cid",
                "best_candidate_title",
                "best_candidate_category",
                "best_candidate_status",
                "best_matching_evidence",
                "best_distance_meters",
            )
            if column in matches.columns
        ],
    ]
    renamed = {
        column: f"maps_specialist_{column}"
        for column in match_columns
        if column not in {"market", "reference_key", "maps_specialist_discovered"}
    }
    match_subset = matches[match_columns].rename(columns=renamed)
    combined = baseline.merge(
        match_subset,
        on=["market", "reference_key"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if not combined["_merge"].eq("both").all():
        raise ValueError("Specialist matches and adjudicated union use different keys")
    combined = combined.drop(columns="_merge")
    combined["source_union_before_specialist"] = combined[
        "source_union_discovered"
    ].astype(bool)
    combined["maps_specialist_discovered"] = combined[
        "maps_specialist_discovered"
    ].astype(bool)
    combined["maps_specialist_incremental"] = (
        ~combined["source_union_before_specialist"]
        & combined["maps_specialist_discovered"]
    )
    combined["source_union_after_specialist"] = (
        combined["source_union_before_specialist"]
        | combined["maps_specialist_discovered"]
    )
    combined["source_status_after_specialist"] = "not_discovered"
    combined.loc[
        combined["source_union_before_specialist"]
        & ~combined["maps_specialist_discovered"],
        "source_status_after_specialist",
    ] = "existing_sources_only"
    combined.loc[
        combined["source_union_before_specialist"]
        & combined["maps_specialist_discovered"],
        "source_status_after_specialist",
    ] = "existing_and_specialist"
    combined.loc[
        combined["maps_specialist_incremental"],
        "source_status_after_specialist",
    ] = "specialist_incremental"

    profile_market = specialist_profile_by_market.set_index("market")
    if set(profile_market.index.astype(str)) != expected:
        raise ValueError("Specialist profile summary markets differ from the frozen set")
    included = combined.loc[combined["current_reference_included"]].copy()
    records: list[dict[str, Any]] = []
    for market in sorted(expected):
        group = included.loc[included["market"].eq(market)]
        reference_count = len(group)
        before = int(group["source_union_before_specialist"].sum())
        specialist = int(group["maps_specialist_discovered"].sum())
        incremental = int(group["maps_specialist_incremental"].sum())
        after = int(group["source_union_after_specialist"].sum())
        before_recall = before / reference_count
        after_recall = after / reference_count

        def decision(value: float) -> str:
            if value >= primary_market_minimum:
                return "meets_primary_market_gate"
            if value < reject_market_below:
                return "discovery_redesign_required"
            return "targeted_gap_audit_required"

        profile = profile_market.loc[market]
        records.append(
            {
                "market": market,
                "current_reference_units": reference_count,
                "source_union_before_specialist_units": before,
                "source_union_before_specialist_recall": before_recall,
                "maps_specialist_discovered_reference_units": specialist,
                "maps_specialist_incremental_reference_units": incremental,
                "source_union_after_specialist_units": after,
                "source_union_after_specialist_recall": after_recall,
                "remaining_unmatched_reference_units": reference_count - after,
                "benchmark_decision_before_specialist": decision(before_recall),
                "benchmark_decision_after_specialist": decision(after_recall),
                "specialist_target_zip_profiles": int(
                    profile["specialist_target_zip_profiles"]
                ),
                "specialist_only_exact_profiles": int(
                    profile["specialist_only_exact_profiles"]
                ),
                "specialist_only_provisional_dental_profiles": int(
                    profile["specialist_only_provisional_dental_profiles"]
                ),
                "specialist_only_manual_category_review_profiles": int(
                    profile["specialist_only_manual_category_review_profiles"]
                ),
            }
        )
    by_market = pd.DataFrame.from_records(records)
    reference_total = int(by_market["current_reference_units"].sum())
    before_total = int(by_market["source_union_before_specialist_units"].sum())
    specialist_total = int(
        by_market["maps_specialist_discovered_reference_units"].sum()
    )
    incremental_total = int(
        by_market["maps_specialist_incremental_reference_units"].sum()
    )
    after_total = int(by_market["source_union_after_specialist_units"].sum())
    changed = by_market["benchmark_decision_before_specialist"].ne(
        by_market["benchmark_decision_after_specialist"]
    )
    summary = {
        "analysis_status": "maps_specialist_zip_identity_and_source_union_audited",
        "api_requests_submitted": 0,
        "market_count": len(expected),
        "current_reference_units": reference_total,
        "source_union_before_specialist_units": before_total,
        "source_union_before_specialist_recall": before_total / reference_total,
        "maps_specialist_discovered_reference_units": specialist_total,
        "maps_specialist_incremental_reference_units": incremental_total,
        "source_union_after_specialist_units": after_total,
        "source_union_after_specialist_recall": after_total / reference_total,
        "source_union_recall_change": (
            after_total / reference_total - before_total / reference_total
        ),
        "remaining_unmatched_reference_units": reference_total - after_total,
        "specialist_target_zip_profiles": int(
            by_market["specialist_target_zip_profiles"].sum()
        ),
        "specialist_only_exact_profiles": int(
            by_market["specialist_only_exact_profiles"].sum()
        ),
        "specialist_only_provisional_dental_profiles": int(
            by_market["specialist_only_provisional_dental_profiles"].sum()
        ),
        "specialist_only_manual_category_review_profiles": int(
            by_market["specialist_only_manual_category_review_profiles"].sum()
        ),
        "markets_by_decision_after_specialist": {
            str(key): int(value)
            for key, value in by_market[
                "benchmark_decision_after_specialist"
            ].value_counts().items()
        },
        "markets_with_benchmark_decision_change": by_market.loc[
            changed, "market"
        ].tolist(),
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
        "interpretation_limits": [
            "Specialist exact-profile uniqueness does not establish physical-location uniqueness.",
            "Historical-reference discovery uses the frozen address, phone, distance, and title rules.",
            "Only specialist matches missing from the adjudicated prior union count as incremental recall.",
        ],
    }
    return (
        combined.sort_values(["market", "reference_key"], ignore_index=True),
        by_market.sort_values("market", ignore_index=True),
        summary,
    )
