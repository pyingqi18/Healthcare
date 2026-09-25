"""Tests for conservative reuse of existing corrected review histories."""

from __future__ import annotations

import pandas as pd

from medical_ratings.existing_review_reuse import build_existing_review_reuse_audit


def _manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "outcome_profile_key": f"google:cid:{cid}",
                "clinic_key": f"google:cid:{cid}",
                "cid": str(cid),
                "place_id": f"place-{cid}",
                "requested_location": "Market",
                "reported_votes_count": votes,
                "planned_depth": depth,
                "estimated_maximum_cost_usd": cost,
            }
            for cid, votes, depth, cost in (
                (1, 2, 60, 0.0045),
                (2, 1, 60, 0.0045),
                (3, 5, 60, 0.0045),
            )
        ]
    )


def _profiles() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "clinic_key": f"google:cid:{cid}",
                "profile_key": f"google:cid:{cid}",
                "cid": str(cid),
                "place_id": f"place-{cid}",
                "title": title,
                "zip": postal,
                "requested_location": "Market",
            }
            for cid, title, postal in (
                (1, "Stable Dental", "10001"),
                (2, "Incomplete Dental", "10002"),
                (3, "Title Match Dental", "10003"),
            )
        ]
    )


def _clinics() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "clinic_key": "old:1",
                "canonical_profile_clinic_key": "google:cid:1",
                "title": "Stable Dental",
                "zip": "10001",
                "search_location": "Market",
                "votes_count": 2,
            },
            {
                "clinic_key": "old:2",
                "canonical_profile_clinic_key": "google:cid:2",
                "title": "Incomplete Dental",
                "zip": "10002",
                "search_location": "Market",
                "votes_count": 3,
            },
            {
                "clinic_key": "old:3",
                "canonical_profile_clinic_key": "",
                "title": "Title Match Dental",
                "zip": "10003",
                "search_location": "Market",
                "votes_count": 1,
            },
        ]
    )


def _reviews() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"clinic_key": "old:1", "source_profile_clinic_key": "google:cid:1", "review_id": "r1", "review_date": "2020-01-01", "rating_numeric": 5},
            {"clinic_key": "old:1", "source_profile_clinic_key": "google:cid:1", "review_id": "r2", "review_date": "2021-01-01", "rating_numeric": 4},
            {"clinic_key": "old:2", "source_profile_clinic_key": "google:cid:2", "review_id": "r3", "review_date": "2022-01-01", "rating_numeric": 5},
            {"clinic_key": "old:3", "source_profile_clinic_key": "google:cid:3", "review_id": "r4", "review_date": "2023-01-01", "rating_numeric": 4},
        ]
    )


def test_reuse_only_complete_stable_profile_history() -> None:
    frames, summary = build_existing_review_reuse_audit(
        _manifest(),
        _profiles(),
        _clinics(),
        _reviews(),
        expected_manifest_rows=3,
    )

    audit = frames["existing_audit"].set_index("existing_clinic_key")
    assert audit.loc["old:1", "reuse_status"] == "reuse_complete_existing_history"
    assert audit.loc["old:2", "reuse_status"] == "stable_match_existing_history_incomplete"
    assert audit.loc["old:3", "reuse_status"] == "title_zip_candidate_not_auto_reused"
    assert frames["reduced_manifest"]["cid"].tolist() == ["2", "3"]
    assert summary["tasks_removed_by_safe_reuse"] == 1
    assert summary["automatic_title_zip_reuse"] == 0


def test_invalid_existing_review_prevents_reuse() -> None:
    reviews = _reviews()
    reviews.loc[0, "rating_numeric"] = 8

    frames, _ = build_existing_review_reuse_audit(
        _manifest(),
        _profiles(),
        _clinics(),
        reviews,
        expected_manifest_rows=3,
    )

    audit = frames["existing_audit"].set_index("existing_clinic_key")
    assert audit.loc["old:1", "reuse_status"] == "stable_match_existing_history_incomplete"


def test_missing_profile_level_review_provenance_prevents_reuse() -> None:
    reviews = _reviews()
    reviews.loc[0, "source_profile_clinic_key"] = ""

    frames, _ = build_existing_review_reuse_audit(
        _manifest(),
        _profiles(),
        _clinics(),
        reviews,
        expected_manifest_rows=3,
    )

    audit = frames["existing_audit"].set_index("existing_clinic_key")
    assert audit.loc["old:1", "reuse_status"] == "stable_match_existing_history_incomplete"
