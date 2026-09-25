from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.maps_specialist_source_audit import (
    build_existing_profile_index,
    compare_specialist_profiles,
    extend_adjudicated_source_union,
)


MARKETS = {"Market_A", "Market_B"}


def existing(source: str) -> pd.DataFrame:
    keys = ["shared", f"{source}-only-a", f"{source}-only-b"]
    return pd.DataFrame(
        {
            "requested_location": ["Market_A", "Market_A", "Market_B"],
            "profile_key": keys,
            "market_assignment_status": ["eligible_target_zip"] * 3,
        }
    )


def specialist() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "requested_location": ["Market_A", "Market_A", "Market_B"],
            "profile_key": ["shared", "specialist-a", "specialist-b"],
            "market_assignment_status": ["eligible_target_zip"] * 3,
            "eligibility_review_status": [
                "include_dental_provider",
                "include_dental_provider",
                "manual_category_review",
            ],
        }
    )


def baseline_union() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": ["Market_A", "Market_A", "Market_B", "Market_B"],
            "reference_key": ["a1", "a2", "b1", "b2"],
            "business_listings_discovered": [True, False, True, False],
            "maps_standard_discovered": [False, False, False, False],
            "source_union_discovered": [True, False, True, False],
            "current_reference_included": [True, True, True, False],
        }
    )


def specialist_matches() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": ["Market_A", "Market_A", "Market_B", "Market_B"],
            "reference_key": ["a1", "a2", "b1", "b2"],
            "discovered": [True, True, False, True],
            "best_candidate_key": ["p1", "p2", None, "p4"],
        }
    )


def profile_market_summary() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": ["Market_A", "Market_B"],
            "specialist_target_zip_profiles": [2, 1],
            "specialist_only_exact_profiles": [1, 1],
            "specialist_only_provisional_dental_profiles": [1, 0],
            "specialist_only_manual_category_review_profiles": [0, 1],
        }
    )


def test_exact_profile_overlap_keeps_specialist_only_profiles_separate() -> None:
    index = build_existing_profile_index(
        existing("business"), existing("maps"), expected_markets=MARKETS
    )
    compared, by_market = compare_specialist_profiles(
        specialist(), index, expected_markets=MARKETS
    )
    keyed = compared.set_index("profile_key")
    assert keyed.loc["shared", "seen_in_any_existing_source"]
    assert not keyed.loc["specialist-a", "seen_in_any_existing_source"]
    assert by_market["specialist_only_exact_profiles"].sum() == 2


def test_union_counts_only_previously_missing_specialist_matches_as_incremental() -> None:
    combined, by_market, summary = extend_adjudicated_source_union(
        baseline_union(),
        specialist_matches(),
        profile_market_summary(),
        expected_markets=MARKETS,
        primary_market_minimum=0.9,
        reject_market_below=0.8,
    )
    keyed = combined.set_index("reference_key")
    assert not keyed.loc["a1", "maps_specialist_incremental"]
    assert keyed.loc["a2", "maps_specialist_incremental"]
    assert summary["current_reference_units"] == 3
    assert summary["source_union_before_specialist_units"] == 2
    assert summary["maps_specialist_incremental_reference_units"] == 1
    assert summary["source_union_after_specialist_units"] == 3
    assert summary["remaining_unmatched_reference_units"] == 0
    assert by_market.loc[
        by_market["market"].eq("Market_A"),
        "source_union_after_specialist_recall",
    ].iloc[0] == 1.0


def test_denominator_exclusion_is_not_reintroduced_by_specialist_match() -> None:
    combined, _, summary = extend_adjudicated_source_union(
        baseline_union(),
        specialist_matches(),
        profile_market_summary(),
        expected_markets=MARKETS,
        primary_market_minimum=0.9,
        reject_market_below=0.8,
    )
    excluded = combined.loc[combined["reference_key"].eq("b2")].iloc[0]
    assert excluded["maps_specialist_discovered"]
    assert not excluded["current_reference_included"]
    assert summary["current_reference_units"] == 3


def test_duplicate_reference_keys_are_rejected() -> None:
    duplicated = pd.concat(
        [specialist_matches(), specialist_matches().iloc[[0]]], ignore_index=True
    )
    with pytest.raises(ValueError, match="duplicate reference keys"):
        extend_adjudicated_source_union(
            baseline_union(),
            duplicated,
            profile_market_summary(),
            expected_markets=MARKETS,
            primary_market_minimum=0.9,
            reject_market_below=0.8,
        )
