"""Tests for the LA/NYC three-way source audit."""

from __future__ import annotations

import pandas as pd

from medical_ratings.business_listings_comparison import (
    match_reference_locations,
    prepare_pilot_candidates,
)
from medical_ratings.major_metro_source_audit import (
    build_major_metro_three_way_summary,
    compare_major_metro_exact_profiles,
    match_reference_locations_indexed,
)


def reviewed_sources() -> tuple[pd.DataFrame, pd.DataFrame]:
    business = pd.DataFrame(
        [
            {
                "requested_location": market,
                "profile_key": key,
                "eligibility_review_status": status,
                "market_assignment_status": "eligible_target_zip",
            }
            for market, key, status in [
                ("LA_CA_L", "google:cid:1", "include_dental_provider"),
                ("LA_CA_L", "google:cid:2", "exclude_non_dentist_category"),
                ("NYC_NY_L", "google:cid:3", "include_dental_provider"),
            ]
        ]
    )
    maps = pd.DataFrame(
        [
            {
                "requested_location": market,
                "profile_key": key,
                "eligibility_review_status": "include_dental_provider",
                "market_assignment_status": "eligible_target_zip",
                "business_listings_market_covered": False,
                "maps_source_status": "business_listings_market_not_covered",
            }
            for market, key in [
                ("LA_CA_L", "google:cid:1"),
                ("LA_CA_L", "google:cid:2"),
                ("NYC_NY_L", "google:cid:4"),
            ]
        ]
    )
    return business, maps


def test_exact_overlap_replaces_stale_major_metro_status() -> None:
    business, maps = reviewed_sources()
    compared, market = compare_major_metro_exact_profiles(business, maps)
    status = compared.set_index("profile_key")["maps_business_exact_profile_status"]
    assert status["google:cid:1"] == "included_in_business_listings"
    assert status["google:cid:2"] == "seen_but_not_included_in_business_listings"
    assert status["google:cid:4"] == "maps_only_exact_profile"
    assert market["maps_only_exact_profiles"].sum() == 1


def test_summary_compares_both_sources_to_one_fused_reference() -> None:
    business, maps = reviewed_sources()
    _, exact_market = compare_major_metro_exact_profiles(business, maps)
    universe = pd.DataFrame(
        [
            {
                "search_location": market,
                "reference_geography_status": "eligible_target_zip",
            }
            for market in ["LA_CA_L", "NYC_NY_L"]
        ]
    )
    business_matches = pd.DataFrame(
        [
            {"market": "LA_CA_L", "discovered": True},
            {"market": "NYC_NY_L", "discovered": True},
        ]
    )
    maps_matches = pd.DataFrame(
        [
            {"market": "LA_CA_L", "discovered": True},
            {"market": "NYC_NY_L", "discovered": False},
        ]
    )
    _, summary = build_major_metro_three_way_summary(
        business,
        maps,
        exact_market,
        universe,
        business_matches,
        maps_matches,
    )
    assert summary["business_listings_fused_reference_recall"] == 1.0
    assert summary["maps_standard_fused_reference_recall"] == 0.5
    assert summary["historical_reference_composition"] == (
        "legacy_plus_external_already_fused"
    )
    assert summary["historical_component_origin_separable_in_crosswalk"] is False
    assert summary["matching_engine"] == "indexed_haversine_candidate_search"
    assert summary["regression_balltree_modified"] is False
    assert summary["automatic_profile_or_location_merges"] == 0


def test_indexed_matcher_equals_existing_vectorized_rules() -> None:
    candidates = pd.DataFrame(
        [
            {
                "profile_key": f"google:cid:{index}",
                "cid": str(index),
                "place_id": f"place-{index}",
                "requested_location": market,
                "title": title,
                "category": "Dentist",
                "address": address,
                "zip": zip_code,
                "latitude": latitude,
                "longitude": longitude,
                "phone": phone,
                "domain": None,
            }
            for index, market, title, address, zip_code, latitude, longitude, phone in [
                (1, "LA_CA_L", "LA Dental", "1 Main St", "90001", 33.97, -118.25, "2131112222"),
                (2, "NYC_NY_L", "NYC Dental", "2 Main St", "10001", 40.75, -73.99, "2121112222"),
            ]
        ]
    )
    regions = {
        "LA_CA_L": {"zip_ranges": [[90000, 91699]]},
        "NYC_NY_L": {"zip_ranges": [[10000, 11699]]},
    }
    rules = pd.DataFrame(
        [{"category": "Dentist", "category_decision": "include", "reason": "dental"}]
    )
    reviewed = prepare_pilot_candidates(
        candidates, regions, rules, target_markets={"LA_CA_L", "NYC_NY_L"}
    )
    references = pd.DataFrame(
        [
            {
                "clinic_key": f"fused:{index}",
                "search_location": market,
                "title": title,
                "address": address,
                "zip": zip_code,
                "latitude": latitude,
                "longitude": longitude,
                "phone": phone,
                "domain": None,
            }
            for index, market, title, address, zip_code, latitude, longitude, phone in [
                (1, "LA_CA_L", "LA Dental", "1 Main St", "90001", 33.97, -118.25, "2131112222"),
                (2, "NYC_NY_L", "NYC Dental", "2 Main St", "10001", 40.75, -73.99, "2121112222"),
            ]
        ]
    )
    expected_matches, expected_pairs = match_reference_locations(
        reviewed,
        references,
        reference_key_prefix=None,
        target_markets={"LA_CA_L", "NYC_NY_L"},
    )
    actual_matches, actual_pairs = match_reference_locations_indexed(
        reviewed,
        references,
        reference_key_prefix=None,
        target_markets={"LA_CA_L", "NYC_NY_L"},
    )
    pd.testing.assert_frame_equal(actual_matches, expected_matches)
    pd.testing.assert_frame_equal(
        actual_pairs.sort_values(["reference_key", "candidate_key"]).reset_index(drop=True),
        expected_pairs.sort_values(["reference_key", "candidate_key"]).reset_index(drop=True),
    )
