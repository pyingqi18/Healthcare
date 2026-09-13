"""Tests for dry-run Google Reviews collection planning."""

import pandas as pd

from medical_ratings.review_collection import (
    build_review_collection_manifest,
    summarize_review_collection_manifest,
)


def locations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "final_physical_location_id": "location:1",
                "clinic_key": "google:cid:100",
                "cid": "100",
                "place_id": "place-100",
                "title": "Known Reviews Dental",
                "mapped_location": "Syracuse_NY_M",
                "votes_count": 61,
                "final_location_canonical": True,
            },
            {
                "final_physical_location_id": "location:2",
                "clinic_key": "google:cid:200",
                "cid": "200",
                "place_id": None,
                "title": "Missing Reviews Dental",
                "mapped_location": "Malone_NY_S",
                "votes_count": None,
                "final_location_canonical": True,
            },
        ]
    )


def codes() -> dict[str, int]:
    return {"Malone_NY_S": 1023114, "Syracuse_NY_M": 1023416}


def test_manifest_uses_one_canonical_location_and_adaptive_depth() -> None:
    manifest = build_review_collection_manifest(locations(), codes())
    known = manifest.set_index("cid").loc["100"]
    missing = manifest.set_index("cid").loc["200"]

    assert len(manifest) == 2
    assert known["identifier_type"] == "place_id"
    assert known["identifier_value"] == "place-100"
    assert int(known["planned_depth"]) == 120
    assert missing["identifier_type"] == "cid"
    assert int(missing["planned_depth"]) == 20
    assert missing["depth_source"] == "missing_votes_minimum"


def test_manifest_applies_depth_cap() -> None:
    frame = locations().iloc[[0]].copy()
    frame["votes_count"] = 5000

    manifest = build_review_collection_manifest(frame, codes())

    assert int(manifest.iloc[0]["planned_depth"]) == 2000
    assert bool(manifest.iloc[0]["depth_capped"])


def test_summary_reports_batches_depth_and_cost() -> None:
    manifest = build_review_collection_manifest(locations(), codes())
    summary = summarize_review_collection_manifest(
        manifest, configured_batch_size=1
    )

    assert summary["planned_tasks"] == 2
    assert summary["planned_post_batches"] == 2
    assert summary["total_planned_depth"] == 140
    assert summary["tasks_with_place_id"] == 1
    assert summary["tasks_using_cid_fallback"] == 1
    assert summary["estimated_maximum_cost_usd"] == 0.0105


def test_manifest_rejects_noncanonical_location_rows() -> None:
    frame = locations()
    frame.loc[0, "final_location_canonical"] = False

    try:
        build_review_collection_manifest(frame, codes())
    except ValueError as error:
        assert "must be canonical" in str(error)
    else:
        raise AssertionError("Expected noncanonical row to fail")
