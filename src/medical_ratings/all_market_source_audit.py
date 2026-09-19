"""Build one uniform three-source audit across all configured markets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from medical_ratings.major_metro_source_audit import (
    match_reference_locations_indexed,
)


REQUIRED_REVIEWED_COLUMNS = {
    "requested_location",
    "profile_key",
    "clinic_key",
    "cid",
    "title",
    "category",
    "address",
    "latitude",
    "longitude",
    "phone",
    "mapped_location",
    "market_assignment_status",
    "eligibility_review_status",
}


def combine_business_listings_sources(
    sources: Mapping[str, pd.DataFrame],
    expected_markets_by_source: Mapping[str, set[str]],
) -> pd.DataFrame:
    """Combine frozen Business Listings stages and prove market ownership."""

    if set(sources) != set(expected_markets_by_source):
        raise ValueError("Business source names differ from the frozen source map")
    frames: list[pd.DataFrame] = []
    all_expected: set[str] = set()
    for source_name, source in sources.items():
        missing = REQUIRED_REVIEWED_COLUMNS - set(source.columns)
        if missing:
            raise KeyError(
                f"{source_name} is missing reviewed columns: {sorted(missing)}"
            )
        expected = {str(value).strip() for value in expected_markets_by_source[source_name]}
        if not expected or any(not value for value in expected):
            raise ValueError(f"{source_name} has an empty expected market set")
        overlap = all_expected & expected
        if overlap:
            raise ValueError(f"Markets are assigned to multiple sources: {sorted(overlap)}")
        all_expected |= expected
        frame = source.copy()
        actual = set(frame["requested_location"].dropna().astype(str))
        if actual != expected:
            raise ValueError(
                f"{source_name} markets differ from the frozen source map: "
                f"actual={sorted(actual)}, expected={sorted(expected)}"
            )
        if frame.duplicated(["requested_location", "profile_key"]).any():
            raise ValueError(f"{source_name} contains duplicate market-profile keys")
        frame["business_listings_source_stage"] = source_name
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if combined.duplicated(["requested_location", "profile_key"]).any():
        raise ValueError("Combined Business Listings sources overlap by market-profile key")
    actual_all = set(combined["requested_location"].dropna().astype(str))
    if actual_all != all_expected:
        raise ValueError("Combined Business Listings markets are incomplete")
    return combined.sort_values(
        ["requested_location", "profile_key"], ignore_index=True
    )


def compare_exact_profiles(
    business_reviewed: pd.DataFrame,
    maps_reviewed: pd.DataFrame,
    *,
    expected_markets: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare target-ZIP profiles by exact Google identity in every market."""

    required = {
        "requested_location",
        "profile_key",
        "market_assignment_status",
        "eligibility_review_status",
    }
    expected = {str(value).strip() for value in expected_markets}
    for label, frame in [
        ("Business Listings", business_reviewed),
        ("Maps Standard", maps_reviewed),
    ]:
        missing = required - set(frame.columns)
        if missing:
            raise KeyError(f"{label} is missing columns: {sorted(missing)}")
        actual = set(frame["requested_location"].dropna().astype(str))
        if actual != expected:
            raise ValueError(f"{label} markets differ from the frozen 15-market set")
        if frame.duplicated(["requested_location", "profile_key"]).any():
            raise ValueError(f"{label} contains duplicate market-profile keys")

    business = business_reviewed.loc[
        business_reviewed["market_assignment_status"].eq("eligible_target_zip"),
        [
            "requested_location",
            "profile_key",
            "eligibility_review_status",
            "business_listings_source_stage",
        ],
    ].copy()
    business["business_listings_profile_seen"] = True
    business["business_listings_profile_included"] = business[
        "eligibility_review_status"
    ].eq("include_dental_provider")
    business = business.rename(
        columns={
            "eligibility_review_status": "business_listings_eligibility_status"
        }
    )
    maps = maps_reviewed.loc[
        maps_reviewed["market_assignment_status"].eq("eligible_target_zip")
    ].copy()
    stale = [
        "business_listings_source_stage",
        "business_listings_profile_seen",
        "business_listings_profile_included",
        "maps_business_exact_profile_status",
    ]
    maps = maps.drop(columns=[column for column in stale if column in maps])
    compared = maps.merge(
        business,
        on=["requested_location", "profile_key"],
        how="left",
        validate="one_to_one",
    )
    seen = compared["business_listings_profile_seen"].eq(True)
    included = compared["business_listings_profile_included"].eq(True)
    compared["business_listings_profile_seen"] = seen.astype(bool)
    compared["business_listings_profile_included"] = included.astype(bool)
    compared["maps_business_exact_profile_status"] = "maps_only_exact_profile"
    compared.loc[seen, "maps_business_exact_profile_status"] = (
        "seen_but_not_included_in_business_listings"
    )
    compared.loc[included, "maps_business_exact_profile_status"] = (
        "included_in_business_listings"
    )

    rows: list[dict[str, Any]] = []
    for market in sorted(expected):
        group = compared.loc[compared["requested_location"].eq(market)]
        rows.append(
            {
                "market": market,
                "maps_standard_target_zip_profiles": len(group),
                "maps_exact_profile_seen_in_business_listings": int(
                    group["business_listings_profile_seen"].sum()
                ),
                "maps_exact_profile_included_in_business_listings": int(
                    group["business_listings_profile_included"].sum()
                ),
                "maps_seen_but_not_included_profiles": int(
                    group["maps_business_exact_profile_status"]
                    .eq("seen_but_not_included_in_business_listings")
                    .sum()
                ),
                "maps_only_exact_profiles": int(
                    group["maps_business_exact_profile_status"]
                    .eq("maps_only_exact_profile")
                    .sum()
                ),
            }
        )
    return compared.reset_index(drop=True), pd.DataFrame.from_records(rows)


def match_each_market(
    reviewed: pd.DataFrame,
    eligible_references: pd.DataFrame,
    *,
    expected_markets: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply one frozen identity rule separately inside every market."""

    matches: list[pd.DataFrame] = []
    pairs: list[pd.DataFrame] = []
    for market in sorted(expected_markets):
        market_reviewed = reviewed.loc[
            reviewed["requested_location"].eq(market)
        ].copy()
        market_references = eligible_references.loc[
            eligible_references["search_location"].eq(market)
        ].copy()
        market_matches, market_pairs = match_reference_locations_indexed(
            market_reviewed,
            market_references,
            reference_key_prefix=None,
            target_markets={market},
        )
        matches.append(market_matches)
        pairs.append(market_pairs)
    return pd.concat(matches, ignore_index=True), pd.concat(pairs, ignore_index=True)


def build_all_market_summary(
    business_reviewed: pd.DataFrame,
    maps_reviewed: pd.DataFrame,
    exact_overlap_by_market: pd.DataFrame,
    fused_reference_universe: pd.DataFrame,
    business_reference_matches: pd.DataFrame,
    maps_reference_matches: pd.DataFrame,
    *,
    expected_markets: set[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build weighted 15-market metrics without treating profiles as locations."""

    exact_index = exact_overlap_by_market.set_index("market")
    records: list[dict[str, Any]] = []
    for market in sorted(expected_markets):
        business = business_reviewed.loc[
            business_reviewed["requested_location"].eq(market)
        ]
        maps = maps_reviewed.loc[maps_reviewed["requested_location"].eq(market)]
        universe = fused_reference_universe.loc[
            fused_reference_universe["search_location"].eq(market)
        ]
        business_matches = business_reference_matches.loc[
            business_reference_matches["market"].eq(market)
        ]
        maps_matches = maps_reference_matches.loc[
            maps_reference_matches["market"].eq(market)
        ]
        exact = exact_index.loc[market]
        eligible = int(
            universe["reference_geography_status"].eq("eligible_target_zip").sum()
        )
        business_discovered = int(business_matches["discovered"].sum())
        maps_discovered = int(maps_matches["discovered"].sum())
        maps_profiles = int(exact["maps_standard_target_zip_profiles"])
        exact_seen = int(exact["maps_exact_profile_seen_in_business_listings"])
        source_stages = sorted(
            set(business["business_listings_source_stage"].dropna().astype(str))
        )
        if len(source_stages) != 1:
            raise ValueError(f"{market} must have exactly one Business Listings stage")
        records.append(
            {
                "market": market,
                "business_listings_source_stage": source_stages[0],
                "business_listings_unique_profiles": len(business),
                "business_listings_target_zip_profiles": int(
                    business["market_assignment_status"].eq("eligible_target_zip").sum()
                ),
                "maps_standard_unique_profiles": len(maps),
                "maps_standard_target_zip_profiles": maps_profiles,
                "fused_historical_units_labeled_as_market": len(universe),
                "fused_historical_target_zip_units": eligible,
                "fused_historical_outside_target_zip_units": int(
                    universe["reference_geography_status"].eq("outside_target_zip").sum()
                ),
                "fused_historical_missing_zip_units": int(
                    universe["reference_geography_status"].eq("missing_zip").sum()
                ),
                "business_listings_discovered_fused_units": business_discovered,
                "business_listings_fused_reference_recall": (
                    business_discovered / eligible if eligible else None
                ),
                "maps_standard_discovered_fused_units": maps_discovered,
                "maps_standard_fused_reference_recall": (
                    maps_discovered / eligible if eligible else None
                ),
                "maps_exact_profile_seen_in_business_listings": exact_seen,
                "maps_business_exact_profile_overlap": (
                    exact_seen / maps_profiles if maps_profiles else None
                ),
                "maps_only_exact_profiles": int(exact["maps_only_exact_profiles"]),
            }
        )
    by_market = pd.DataFrame.from_records(records)
    reference_total = int(by_market["fused_historical_target_zip_units"].sum())
    business_total = int(
        by_market["business_listings_discovered_fused_units"].sum()
    )
    maps_total = int(by_market["maps_standard_discovered_fused_units"].sum())
    maps_profiles = int(by_market["maps_standard_target_zip_profiles"].sum())
    exact_total = int(
        by_market["maps_exact_profile_seen_in_business_listings"].sum()
    )
    if reference_total == 0 or maps_profiles == 0:
        raise ValueError("Uniform summary requires nonzero reference and Maps totals")
    summary = {
        "analysis_status": "all_15_markets_three_way_source_audit_not_final",
        "api_requests_submitted": 0,
        "markets_audited": sorted(expected_markets),
        "market_count": len(expected_markets),
        "historical_reference_name": "corrected_v1_fused_historical_reference",
        "historical_reference_composition": "legacy_plus_external_already_fused",
        "uniform_reference_denominator": "target_zip_competition_units_before_current_validity_adjudication",
        "pilot_current_validity_denominator_mixed_into_uniform_summary": False,
        "fused_historical_target_zip_units": reference_total,
        "business_listings_discovered_fused_units": business_total,
        "business_listings_fused_reference_recall": business_total / reference_total,
        "maps_standard_discovered_fused_units": maps_total,
        "maps_standard_fused_reference_recall": maps_total / reference_total,
        "maps_standard_target_zip_profiles": maps_profiles,
        "maps_exact_profile_seen_in_business_listings": exact_total,
        "maps_business_exact_profile_overlap": exact_total / maps_profiles,
        "maps_only_exact_profiles": int(by_market["maps_only_exact_profiles"].sum()),
        "matching_rule": "frozen_address_phone_distance_and_title_identity_rules",
        "matching_engine": "indexed_haversine_candidate_search",
        "regression_balltree_modified": False,
        "automatic_profile_or_location_merges": 0,
        "interpretation_limits": [
            "The historical reference already fuses legacy and external records.",
            "Maps Standard contains two core keyword tasks per market and is a supplement, not a census.",
            "Exact cross-source overlap identifies Google profiles rather than physical locations.",
            "Pilot current-validity adjudication remains separate from the uniform 15-market denominator.",
        ],
    }
    return by_market, summary
