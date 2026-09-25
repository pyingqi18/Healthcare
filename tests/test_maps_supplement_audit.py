"""Tests for Maps actual-ZIP review and exact cross-source profile overlap."""

from __future__ import annotations

import pandas as pd

from medical_ratings.maps_supplement_audit import (
    audit_maps_candidates,
    build_business_listings_profile_index,
    compare_maps_with_business_listings,
    recover_missing_maps_zip,
)


def regions() -> dict[str, dict[str, object]]:
    return {
        "Market_A": {"zip_values": [12345]},
        "Market_B": {"zip_values": [54321]},
    }


def category_rules() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "category": "Dentist",
                "category_decision": "include",
                "reason": "Dental provider",
            },
            {
                "category": "Medical clinic",
                "category_decision": "manual_review",
                "reason": "Needs review",
            },
        ]
    )


def maps_candidates() -> pd.DataFrame:
    base = {
        "cid": pd.NA,
        "place_id": pd.NA,
        "title": "Clinic",
        "address": "1 Main St",
        "latitude": 1.0,
        "longitude": 2.0,
        "phone": pd.NA,
        "domain": pd.NA,
        "country_code": "US",
        "primary_legacy_category_group": "keywords_General_Dentist",
    }
    return pd.DataFrame(
        [
            {
                **base,
                "profile_key": "google:cid:1",
                "requested_location": "Market_A",
                "zip": "12345",
                "category": "Dentist",
            },
            {
                **base,
                "profile_key": "google:cid:2",
                "requested_location": "Market_A",
                "zip": "99999",
                "category": "Dentist",
            },
            {
                **base,
                "profile_key": "google:cid:3",
                "requested_location": "Market_B",
                "zip": "54321",
                "category": "Medical clinic",
                "primary_legacy_category_group": "Unclassified",
            },
        ]
    )


def test_maps_audit_uses_actual_zip_and_keeps_all_profiles() -> None:
    reviewed = audit_maps_candidates(maps_candidates(), regions(), category_rules())
    status = reviewed.set_index("profile_key")
    assert len(reviewed) == 3
    assert status.loc["google:cid:1", "maps_target_zip_eligible"]
    assert not status.loc["google:cid:2", "maps_target_zip_eligible"]
    assert (
        status.loc["google:cid:3", "eligibility_review_status"]
        == "manual_category_review"
    )


def test_maps_audit_recovers_missing_zip_from_address_suffix() -> None:
    candidate = maps_candidates().iloc[[0]].copy()
    candidate["zip"] = pd.NA
    candidate["address"] = "10 Main St, Example, NY 12345"
    reviewed = audit_maps_candidates(candidate, regions(), category_rules())
    row = reviewed.iloc[0]
    assert row["normalized_zip"] == "12345"
    assert row["zip_resolution_method"] == "address_text_fallback"
    assert row["market_assignment_status"] == "eligible_target_zip"


def test_maps_zip_recovery_does_not_replace_nonblank_source_zip() -> None:
    candidate = maps_candidates().iloc[[0]].copy()
    candidate["zip"] = "99999"
    candidate["address"] = "10 Main St, Example, NY 12345"
    recovered = recover_missing_maps_zip(candidate)
    assert recovered.iloc[0]["zip"] == "99999"
    assert recovered.iloc[0]["zip_resolution_method"] == "source_zip_field"


def test_maps_zip_recovery_ignores_unstructured_five_digit_text() -> None:
    candidate = maps_candidates().iloc[[0]].copy()
    candidate["zip"] = pd.NA
    candidate["address"] = "Suite 12345, no city or state suffix"
    recovered = recover_missing_maps_zip(candidate)
    assert pd.isna(recovered.iloc[0]["zip"])
    assert recovered.iloc[0]["zip_resolution_method"] == "unresolved"


def test_business_listings_index_uses_explicit_inclusion_columns() -> None:
    pilot = pd.DataFrame(
        {
            "requested_location": ["Market_A", "Market_A"],
            "clinic_key": ["google:cid:1", "google:cid:9"],
            "competition_candidate_included": [True, False],
        }
    )
    rollout = pd.DataFrame(
        {
            "requested_location": ["Market_B"],
            "clinic_key": ["google:cid:8"],
            "provisional_profile_included": ["True"],
        }
    )
    index = build_business_listings_profile_index(
        [("pilot", pilot), ("rollout", rollout)]
    )
    assert set(index["profile_key"]) == {
        "google:cid:1",
        "google:cid:8",
        "google:cid:9",
    }
    status = index.set_index("profile_key")["business_listings_profile_included"]
    assert status.loc["google:cid:1"]
    assert not status.loc["google:cid:9"]


def test_exact_source_comparison_does_not_merge_physical_locations() -> None:
    reviewed = audit_maps_candidates(maps_candidates(), regions(), category_rules())
    business = build_business_listings_profile_index(
        [
            (
                "pilot",
                pd.DataFrame(
                    {
                        "requested_location": ["Market_A"],
                        "clinic_key": ["google:cid:1"],
                        "competition_candidate_included": [True],
                    }
                ),
            )
        ]
    )
    compared, market, summary = compare_maps_with_business_listings(
        reviewed, business
    )
    assert len(compared) == 2
    assert compared["exact_profile_seen_in_business_listings"].sum() == 1
    assert compared["exact_profile_included_in_business_listings"].sum() == 1
    assert market.set_index("market").loc["Market_B", "maps_only_exact_profiles"] == 1
    assert summary["business_listings_uncovered_maps_markets"] == ["Market_B"]
    assert summary["automatic_profile_or_location_merges"] == 0


def test_seen_but_excluded_business_profile_is_not_called_maps_only() -> None:
    reviewed = audit_maps_candidates(maps_candidates(), regions(), category_rules())
    business = build_business_listings_profile_index(
        [
            (
                "rollout",
                pd.DataFrame(
                    {
                        "requested_location": ["Market_B"],
                        "clinic_key": ["google:cid:3"],
                        "provisional_profile_included": [False],
                    }
                ),
            )
        ]
    )
    compared, _, _ = compare_maps_with_business_listings(reviewed, business)
    row = compared.set_index("profile_key").loc["google:cid:3"]
    assert row["exact_profile_seen_in_business_listings"]
    assert not row["exact_profile_included_in_business_listings"]
    assert row["maps_source_status"] == "seen_but_not_included_in_business_listings"
