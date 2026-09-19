"""Tests for Maps-only queue triage and cross-source identity evidence."""

from __future__ import annotations

import pandas as pd

from medical_ratings.maps_only_review import (
    build_maps_business_identity_pairs,
    combine_business_listings_profiles,
    summarize_maps_only_review,
    triage_maps_profile_review,
)


def profile_audit() -> pd.DataFrame:
    base = {
        "requested_location": "Market_A",
        "address": "1 Main St",
        "latitude": 1.0,
        "longitude": 2.0,
        "phone": "555-111-2222",
        "domain": "clinic.example",
        "business_listings_market_covered": True,
        "maps_source_status": "maps_only_exact_profile",
    }
    return pd.DataFrame(
        [
            {
                **base,
                "profile_key": "maps:1",
                "title": "Clinic One",
                "category": "Dentist",
                "eligibility_review_status": "include_dental_provider",
            },
            {
                **base,
                "profile_key": "maps:2",
                "title": "Jane Doe DDS",
                "category": "Medical clinic",
                "eligibility_review_status": "manual_category_review",
            },
            {
                **base,
                "profile_key": "maps:3",
                "title": "Pet Hospital",
                "category": "Animal hospital",
                "eligibility_review_status": "manual_category_review",
            },
            {
                **base,
                "profile_key": "maps:4",
                "title": "Urgent Dental Care",
                "category": "Urgent care center",
                "eligibility_review_status": "exclude_non_dentist_category",
            },
            {
                **base,
                "profile_key": "maps:5",
                "title": "Already seen",
                "category": "Dentist",
                "eligibility_review_status": "include_dental_provider",
                "maps_source_status": "included_in_business_listings",
            },
            {
                **base,
                "profile_key": "maps:6",
                "title": "Los Angeles Dental Center",
                "category": "Dental clinic",
                "eligibility_review_status": "include_dental_provider",
                "requested_location": "Market_B",
                "business_listings_market_covered": False,
            },
        ]
    )


def test_triage_separates_true_maps_only_and_uncovered_markets() -> None:
    triaged = triage_maps_profile_review(profile_audit()).set_index("profile_key")
    assert triaged.loc["maps:1", "maps_review_queue"] == "candidate_identity_review"
    assert (
        triaged.loc["maps:2", "maps_review_queue"]
        == "manual_provider_title_conflict"
    )
    assert triaged.loc["maps:3", "maps_review_queue"] == "manual_likely_nonprovider"
    assert (
        triaged.loc["maps:4", "maps_review_queue"]
        == "excluded_provider_title_conflict"
    )
    assert triaged.loc["maps:5", "maps_review_queue"] == "already_seen_in_business_listings"
    assert triaged.loc["maps:6", "maps_review_queue"] == "await_business_listings_primary"
    assert not triaged["automatic_category_decision"].any()


def test_cross_source_pairs_require_review_and_do_not_merge() -> None:
    triaged = triage_maps_profile_review(profile_audit())
    business = combine_business_listings_profiles(
        [
            (
                "rollout",
                pd.DataFrame(
                    {
                        "requested_location": ["Market_A"],
                        "clinic_key": ["business:1"],
                        "title": ["Clinic One Dental"],
                        "address": ["1 Main St"],
                        "latitude": [1.0],
                        "longitude": [2.0],
                        "phone": ["5551112222"],
                        "domain": ["clinic.example"],
                        "provisional_profile_included": [True],
                    }
                ),
            )
        ]
    )
    pairs = build_maps_business_identity_pairs(triaged, business)
    assert "maps:1" in set(pairs["maps_profile_key"])
    assert pairs["review_decision"].eq("pending_manual_review").all()
    summary = summarize_maps_only_review(triaged, pairs)
    assert summary["true_maps_only_profiles_in_covered_markets"] == 4
    assert summary["uncovered_market_profiles"] == 1
    assert summary["automatic_profile_or_location_merges"] == 0
