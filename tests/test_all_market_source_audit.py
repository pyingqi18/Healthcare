"""Tests for the uniform all-market three-source audit."""

from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.all_market_source_audit import (
    build_all_market_summary,
    combine_business_listings_sources,
    compare_exact_profiles,
)


def reviewed(market: str, key: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "requested_location": market,
                "profile_key": key,
                "clinic_key": key,
                "cid": key,
                "title": "Dental",
                "category": "Dentist",
                "address": "1 Main St",
                "latitude": 40.0,
                "longitude": -75.0,
                "phone": "1112223333",
                "mapped_location": market,
                "market_assignment_status": "eligible_target_zip",
                "eligibility_review_status": "include_dental_provider",
            }
        ]
    )


def test_combined_sources_preserve_one_frozen_stage_per_market() -> None:
    combined = combine_business_listings_sources(
        {
            "pilot": reviewed("small", "google:1"),
            "rollout": reviewed("large", "google:2"),
        },
        {"pilot": {"small"}, "rollout": {"large"}},
    )
    assert set(combined["requested_location"]) == {"small", "large"}
    assert set(combined["business_listings_source_stage"]) == {"pilot", "rollout"}


def test_combined_sources_reject_market_owned_by_two_stages() -> None:
    with pytest.raises(ValueError, match="multiple sources"):
        combine_business_listings_sources(
            {
                "first": reviewed("same", "google:1"),
                "second": reviewed("same", "google:2"),
            },
            {"first": {"same"}, "second": {"same"}},
        )


def test_exact_overlap_uses_profile_identity_not_location_identity() -> None:
    business = combine_business_listings_sources(
        {
            "pilot": reviewed("small", "google:1"),
            "rollout": reviewed("large", "google:2"),
        },
        {"pilot": {"small"}, "rollout": {"large"}},
    )
    maps = pd.concat(
        [reviewed("small", "google:1"), reviewed("large", "google:3")],
        ignore_index=True,
    )
    compared, market = compare_exact_profiles(
        business, maps, expected_markets={"small", "large"}
    )
    status = compared.set_index("profile_key")["maps_business_exact_profile_status"]
    assert status["google:1"] == "included_in_business_listings"
    assert status["google:3"] == "maps_only_exact_profile"
    assert market["maps_only_exact_profiles"].sum() == 1


def test_summary_uses_weighted_uniform_reference_denominator() -> None:
    business = combine_business_listings_sources(
        {
            "pilot": reviewed("small", "google:1"),
            "rollout": reviewed("large", "google:2"),
        },
        {"pilot": {"small"}, "rollout": {"large"}},
    )
    maps = pd.concat(
        [reviewed("small", "google:1"), reviewed("large", "google:3")],
        ignore_index=True,
    )
    _, exact_market = compare_exact_profiles(
        business, maps, expected_markets={"small", "large"}
    )
    universe = pd.DataFrame(
        [
            {"search_location": "small", "reference_geography_status": "eligible_target_zip"},
            {"search_location": "large", "reference_geography_status": "eligible_target_zip"},
            {"search_location": "large", "reference_geography_status": "eligible_target_zip"},
        ]
    )
    business_matches = pd.DataFrame(
        [
            {"market": "small", "discovered": True},
            {"market": "large", "discovered": True},
            {"market": "large", "discovered": False},
        ]
    )
    maps_matches = pd.DataFrame(
        [
            {"market": "small", "discovered": False},
            {"market": "large", "discovered": True},
            {"market": "large", "discovered": False},
        ]
    )
    by_market, summary = build_all_market_summary(
        business,
        maps,
        exact_market,
        universe,
        business_matches,
        maps_matches,
        expected_markets={"small", "large"},
    )
    assert summary["business_listings_fused_reference_recall"] == 2 / 3
    assert summary["maps_standard_fused_reference_recall"] == 1 / 3
    assert summary["pilot_current_validity_denominator_mixed_into_uniform_summary"] is False
    assert summary["regression_balltree_modified"] is False
    assert set(by_market["business_listings_source_stage"]) == {"pilot", "rollout"}
