"""Tests for enhanced reuse of mixed-schema legacy review histories."""

from __future__ import annotations

import pandas as pd

from medical_ratings.enhanced_legacy_review_reuse import (
    build_enhanced_legacy_review_reuse,
)


def _inputs() -> tuple[pd.DataFrame, ...]:
    manifest = pd.DataFrame(
        [
            {"outcome_profile_key": "google:cid:1", "reported_votes_count": 2, "estimated_maximum_cost_usd": 0.01},
            {"outcome_profile_key": "google:cid:2", "reported_votes_count": 1, "estimated_maximum_cost_usd": 0.01},
        ]
    )
    profiles = pd.DataFrame(
        [
            {"profile_key": "google:cid:1", "address": "10 Main Street, Town, NY 10001", "phone": "212-555-1000", "domain": "one.example", "latitude": 40.0, "longitude": -73.0},
            {"profile_key": "google:cid:2", "address": "20 Main Street, Town, NY 10002", "phone": "212-555-2000", "domain": "two.example", "latitude": 40.1, "longitude": -73.1},
        ]
    )
    clinics = pd.DataFrame(
        [
            {"clinic_key": "old:1", "address": "10 Main St, Town, NY 10001", "phone": "(212) 555-1000", "domain": "https://one.example", "latitude": 40.0, "longitude": -73.0},
            {"clinic_key": "old:2", "address": "99 Other Rd, Town, NY 10002", "phone": "212-555-2000", "domain": "two.example", "latitude": 40.1, "longitude": -73.1},
        ]
    )
    reviews = pd.DataFrame(
        [
            {"clinic_key": "old:1", "review_timestamp_utc": pd.NA, "review_date": "2020-01-01", "rating_value": pd.NA, "rating_numeric": 5, "review_id": pd.NA, "review_url": "https://reviews/r1"},
            {"clinic_key": "old:1", "review_timestamp_utc": pd.NA, "review_date": "2021-01-01", "rating_value": pd.NA, "rating_numeric": 4, "review_id": pd.NA, "review_url": "https://reviews/r2"},
            {"clinic_key": "old:2", "review_timestamp_utc": pd.NA, "review_date": "2022-01-01", "rating_value": pd.NA, "rating_numeric": 5, "review_id": pd.NA, "review_url": "https://reviews/r3"},
        ]
    )
    audit = pd.DataFrame(
        [
            {"existing_clinic_key": "old:1", "candidate_outcome_profile_key": "google:cid:1", "reuse_status": "title_zip_candidate_not_auto_reused", "existing_reported_reviews_count": 2},
            {"existing_clinic_key": "old:2", "candidate_outcome_profile_key": "google:cid:2", "reuse_status": "title_zip_candidate_not_auto_reused", "existing_reported_reviews_count": 1},
        ]
    )
    reusable = pd.DataFrame(columns=["candidate_outcome_profile_key"])
    return manifest, profiles, clinics, reviews, audit, reusable


def test_enhanced_reuse_coalesces_legacy_fields_and_requires_exact_address() -> None:
    frames, summary = build_enhanced_legacy_review_reuse(
        *_inputs(), expected_manifest_rows=2
    )
    audit = frames["enhanced_audit"].set_index("existing_clinic_key")
    assert audit.loc["old:1", "enhanced_reuse_status"] == "reuse_enhanced_exact_address_complete_history"
    assert audit.loc["old:1", "valid_review_dates"] == 2
    assert audit.loc["old:1", "valid_review_ratings"] == 2
    assert audit.loc["old:2", "enhanced_reuse_status"] == "enhanced_identity_not_approved"
    assert frames["enhanced_reduced_manifest"]["outcome_profile_key"].tolist() == ["google:cid:2"]
    assert summary["new_enhanced_reusable_profiles"] == 1


def test_conflicting_phone_prevents_enhanced_reuse() -> None:
    manifest, profiles, clinics, reviews, audit, reusable = _inputs()
    clinics.loc[0, "phone"] = "212-555-9999"
    frames, _ = build_enhanced_legacy_review_reuse(
        manifest, profiles, clinics, reviews, audit, reusable, expected_manifest_rows=2
    )
    row = frames["enhanced_audit"].set_index("existing_clinic_key").loc["old:1"]
    assert bool(row["phone_conflict"])
    assert row["enhanced_reuse_status"] == "enhanced_identity_not_approved"


def test_duplicate_review_url_prevents_enhanced_reuse() -> None:
    manifest, profiles, clinics, reviews, audit, reusable = _inputs()
    reviews.loc[1, "review_url"] = reviews.loc[0, "review_url"]
    frames, _ = build_enhanced_legacy_review_reuse(
        manifest, profiles, clinics, reviews, audit, reusable, expected_manifest_rows=2
    )
    row = frames["enhanced_audit"].set_index("existing_clinic_key").loc["old:1"]
    assert row["enhanced_reuse_status"] == "enhanced_existing_history_incomplete"
