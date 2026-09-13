"""Tests for building corrected clinic and review tables."""

import pandas as pd

from medical_ratings.replacement_build import build_corrected_tables


def test_build_replaces_wrong_batches_with_physical_locations() -> None:
    legacy_clinics = pd.DataFrame(
        [
            {"clinic_key": "keep", "title": "Keep", "zip": "10001", "latitude": 40.0, "longitude": -74.0, "earliest_review_date": "2020-01-01", "search_location": "Other", "used_location_code": "1"},
            {"clinic_key": "wrong", "title": "Wrong", "zip": "75001", "latitude": 32.0, "longitude": -96.0, "earliest_review_date": "2021-01-01", "search_location": "Malone_NY_S", "used_location_code": "1026588"},
        ]
    )
    legacy_reviews = pd.DataFrame(
        [{"clinic_key": "keep", "review_date": "2020-01-01", "rating_numeric": 4}, {"clinic_key": "wrong", "review_date": "2021-01-01", "rating_numeric": 5}]
    )
    locations = pd.DataFrame(
        [
            {"final_physical_location_id": "location:new", "clinic_key": "google:cid:1", "title": "New Dental", "zip": "12953", "latitude": 44.8, "longitude": -74.3, "mapped_location": "Malone_NY_S"},
            {"final_physical_location_id": "location:zero", "clinic_key": "google:cid:2", "title": "Zero Dental", "zip": "13202", "latitude": 43.0, "longitude": -76.1, "mapped_location": "Syracuse_NY_M"},
        ]
    )
    new_reviews = pd.DataFrame(
        [{"clinic_key": "google:cid:1", "final_physical_location_id": "location:new", "review_id": "r1", "review_timestamp_utc": "2025-01-02T00:00:00Z", "rating_value": 5}]
    )
    zero = pd.DataFrame([{"final_physical_location_id": "location:zero"}])

    clinics, reviews, summary = build_corrected_tables(
        legacy_clinics, legacy_reviews, locations, new_reviews, zero
    )

    assert set(clinics["clinic_key"]) == {"keep", "location:new", "location:zero"}
    assert "wrong" not in set(reviews["clinic_key"])
    assert "location:new" in set(reviews["clinic_key"])
    assert summary["legacy_clinics_removed"] == 1
    assert summary["legacy_reviews_removed"] == 1
    assert summary["zero_review_locations_preserved"] == 1
    assert summary["new_locations_missing_entry_date"] == 1
    assert summary["output_clinic_rows"] == 3
    assert summary["output_review_rows"] == 2


def test_new_review_uses_physical_location_as_clinic_key() -> None:
    legacy_clinics = pd.DataFrame(
        [{"clinic_key": "keep", "title": "Keep", "zip": "10001", "latitude": 40.0, "longitude": -74.0, "earliest_review_date": "2020-01-01", "search_location": "Other", "used_location_code": "1"}]
    )
    legacy_reviews = pd.DataFrame(
        [{"clinic_key": "keep", "review_date": "2020-01-01", "rating_numeric": 4}]
    )
    locations = pd.DataFrame(
        [{"final_physical_location_id": "location:new", "clinic_key": "google:cid:1", "title": "New Dental", "zip": "12953", "latitude": 44.8, "longitude": -74.3, "mapped_location": "Malone_NY_S"}]
    )
    new_reviews = pd.DataFrame(
        [{"clinic_key": "google:cid:1", "final_physical_location_id": "location:new", "review_id": "r1", "review_timestamp_utc": "2025-01-02T00:00:00Z", "rating_value": 5}]
    )

    _, reviews, _ = build_corrected_tables(
        legacy_clinics, legacy_reviews, locations, new_reviews, pd.DataFrame(columns=["final_physical_location_id"])
    )
    row = reviews.loc[reviews["review_id"].eq("r1")].iloc[0]
    assert row["clinic_key"] == "location:new"
    assert row["source_profile_clinic_key"] == "google:cid:1"
    assert row["review_linkage_method"] == "final_physical_location_id"
