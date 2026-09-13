"""Offline tests for the legacy replacement readiness audit."""

import pandas as pd
import pytest

from medical_ratings.replacement_audit import (
    audit_replacement_inputs,
    validate_expected_replacement_counts,
)


def legacy_clinics() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "clinic_key": "legacy:keep",
                "title": "Existing Practice",
                "zip": "10001",
                "search_location": "New_York_NY_L",
                "used_location_code": "1000001",
            },
            {
                "clinic_key": "legacy:malone",
                "title": "Texas Result",
                "zip": "75001",
                "search_location": "Malone_NY_S",
                "used_location_code": "1026588.0",
            },
            {
                "clinic_key": "legacy:syracuse",
                "title": "Utah Result",
                "zip": "84001",
                "search_location": "Syracuse_NY_M",
                "used_location_code": 1027001,
            },
        ]
    )


def legacy_reviews() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": [
                "legacy:keep",
                "legacy:malone",
                "legacy:syracuse",
                "legacy:syracuse",
            ]
        }
    )


def new_locations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "final_physical_location_id": "location:malone",
                "clinic_key": "google:cid:1",
                "title": "Malone Dental",
                "zip": "12953",
                "mapped_location": "Malone_NY_S",
            },
            {
                "final_physical_location_id": "location:syracuse",
                "clinic_key": "google:cid:2",
                "title": "Syracuse Dental",
                "zip": "13202",
                "mapped_location": "Syracuse_NY_M",
            },
        ]
    )


def new_reviews() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "final_physical_location_id": "location:malone",
                "review_id": "review:1",
                "review_timestamp_utc": "2025-06-01T00:00:00Z",
                "rating_value": 5,
                "requested_location": "Malone_NY_S",
            }
        ]
    )


def zero_reviews() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "final_physical_location_id": "location:syracuse",
                "requested_location": "Syracuse_NY_M",
            }
        ]
    )


def test_audit_counts_exact_removal_and_complete_new_coverage() -> None:
    batches, collisions, summary = audit_replacement_inputs(
        legacy_clinics(),
        legacy_reviews(),
        new_locations(),
        new_reviews(),
        zero_reviews(),
    )

    assert len(batches) == 2
    assert summary["legacy_clinics_to_remove"] == 2
    assert summary["legacy_reviews_to_remove"] == 3
    assert summary["new_physical_locations"] == 2
    assert summary["new_locations_with_reviews"] == 1
    assert summary["new_zero_review_locations"] == 1
    assert summary["projected_clinic_rows"] == 3
    assert summary["projected_review_rows"] == 2
    assert collisions.empty
    assert summary["replacement_ready"] is True


def test_audit_rejects_location_without_review_status() -> None:
    with pytest.raises(ValueError, match="missing review observation status"):
        audit_replacement_inputs(
            legacy_clinics(),
            legacy_reviews(),
            new_locations(),
            new_reviews(),
            zero_reviews().iloc[0:0],
        )


def test_audit_reports_collision_with_unaffected_legacy_location() -> None:
    locations = new_locations()
    locations.loc[0, ["title", "zip"]] = ["Existing Practice", "10001"]
    _, collisions, summary = audit_replacement_inputs(
        legacy_clinics(),
        legacy_reviews(),
        locations,
        new_reviews(),
        zero_reviews(),
    )

    assert len(collisions) == 1
    assert summary["potential_unaffected_legacy_location_collisions"] == 1
    assert summary["replacement_ready"] is False


def test_frozen_count_validation_rejects_changed_input() -> None:
    _, _, summary = audit_replacement_inputs(
        legacy_clinics(),
        legacy_reviews(),
        new_locations(),
        new_reviews(),
        zero_reviews(),
    )
    with pytest.raises(ValueError, match="Replacement counts changed"):
        validate_expected_replacement_counts(
            summary,
            {"legacy_clinics_to_remove": 213},
        )
