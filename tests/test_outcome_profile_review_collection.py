"""Tests for full-rebuild review planning at the outcome-profile level."""

from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.review_collection import (
    build_outcome_profile_review_manifest,
    summarize_outcome_profile_review_manifest,
)


def _profiles() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "clinic_key": "google:cid:1",
                "profile_key": "google:cid:1",
                "cid": "1",
                "place_id": "place-1",
                "title": "Clinic One",
                "requested_location": "Market_A",
                "mapped_location": "Market_A",
                "votes_count": 12,
            },
            {
                "clinic_key": "google:cid:2",
                "profile_key": "google:cid:2",
                "cid": "2",
                "place_id": "",
                "title": "Provider Two",
                "requested_location": "Market_A",
                "mapped_location": "Market_A",
                "votes_count": 5000,
            },
            {
                "clinic_key": "google:cid:3",
                "profile_key": "google:cid:3",
                "cid": "3",
                "place_id": "place-3",
                "title": "No Reviews Dental",
                "requested_location": "Market_B",
                "mapped_location": "Market_B",
                "votes_count": 0,
            },
        ]
    )


def _crosswalk() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "clinic_key": f"google:cid:{cid}",
                "profile_key": f"google:cid:{cid}",
                "cid": str(cid),
                "mapped_location": market,
                "outcome_profile_included": True,
                "competition_location_id": location,
                "address_merge_sensitivity_location_id": f"sensitivity:{location}",
            }
            for cid, market, location in (
                (1, "Market_A", "location:shared"),
                (2, "Market_A", "location:shared"),
                (3, "Market_B", "location:3"),
            )
        ]
    )


def test_manifest_keeps_profiles_separate_inside_one_competition_location() -> None:
    manifest = build_outcome_profile_review_manifest(
        _profiles(),
        _crosswalk(),
        {"Market_A": 101, "Market_B": 102},
        expected_outcome_profiles=3,
    )

    assert len(manifest) == 3
    assert manifest["outcome_profile_key"].nunique() == 3
    assert manifest["competition_location_id"].nunique() == 2
    assert manifest.loc[manifest["cid"].isin(["1", "2"]), "competition_location_id"].eq(
        "location:shared"
    ).all()
    capped = manifest.set_index("cid").loc["2"]
    assert capped["identifier_type"] == "cid"
    assert int(capped["planned_depth"]) == 4490
    assert bool(capped["depth_capped"])
    assert capped["coverage_status_before_collection"] == (
        "planned_api_limit_left_censoring_possible"
    )


def test_manifest_summary_reports_profiles_locations_and_zero_votes() -> None:
    manifest = build_outcome_profile_review_manifest(
        _profiles(),
        _crosswalk(),
        {"Market_A": 101, "Market_B": 102},
        expected_outcome_profiles=3,
    )

    summary = summarize_outcome_profile_review_manifest(
        manifest, configured_batch_size=2
    )

    assert summary["planned_tasks"] == 3
    assert summary["unique_outcome_profiles"] == 3
    assert summary["unique_main_competition_locations"] == 2
    assert summary["reported_zero_profiles"] == 1
    assert summary["tasks_with_capped_depth"] == 1
    assert summary["planned_post_batches"] == 2


def test_manifest_rejects_profile_crosswalk_identity_drift() -> None:
    crosswalk = _crosswalk()
    crosswalk.loc[0, "cid"] = "different"

    with pytest.raises(ValueError, match="cid differs"):
        build_outcome_profile_review_manifest(
            _profiles(),
            crosswalk,
            {"Market_A": 101, "Market_B": 102},
            expected_outcome_profiles=3,
        )


def test_manifest_rejects_profile_crosswalk_market_drift() -> None:
    profiles = _profiles()
    profiles.loc[0, "mapped_location"] = "Wrong_Market"
    profiles.loc[0, "requested_location"] = "Wrong_Market"

    with pytest.raises(ValueError, match="market differs"):
        build_outcome_profile_review_manifest(
            profiles,
            _crosswalk(),
            {"Market_A": 101, "Market_B": 102},
            expected_outcome_profiles=3,
        )
