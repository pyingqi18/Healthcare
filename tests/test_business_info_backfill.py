"""Tests for exact-CID Business Info backfill planning."""

import pandas as pd

from medical_ratings.business_info_backfill import (
    build_business_info_manifest,
    summarize_business_info_manifest,
)


def test_build_business_info_manifest_selects_only_unresolved_candidates() -> None:
    reviewed = pd.DataFrame(
        [
            {
                "clinic_key": "google:cid:100",
                "cid": "100",
                "requested_locations": "Malone_NY_S",
                "market_assignment_status": "local_finder_only_unlocated",
                "eligibility_review_status": "needs_geography",
            },
            {
                "clinic_key": "google:cid:200",
                "cid": "200",
                "requested_locations": "Syracuse_NY_M",
                "market_assignment_status": "maps_missing_zip",
                "eligibility_review_status": "needs_geography",
            },
            {
                "clinic_key": "google:cid:300",
                "cid": "300",
                "requested_locations": "Syracuse_NY_M",
                "market_assignment_status": "eligible_target_zip",
                "eligibility_review_status": "include_dental_provider",
            },
        ]
    )

    manifest = build_business_info_manifest(reviewed)

    assert len(manifest) == 2
    assert set(manifest["cid"]) == {"100", "200"}
    assert set(manifest["query"]) == {"cid:100", "cid:200"}
    assert manifest["task_tag"].is_unique
    assert set(manifest["location_code"]) == {2840}
    assert set(manifest["priority"]) == {1}


def test_summarize_business_info_manifest_calculates_batches_and_cost() -> None:
    reviewed = pd.DataFrame(
        [
            {
                "clinic_key": f"google:cid:{cid}",
                "cid": str(cid),
                "requested_locations": "Syracuse_NY_M",
                "market_assignment_status": "local_finder_only_unlocated",
                "eligibility_review_status": "needs_geography",
            }
            for cid in range(1, 202)
        ]
    )
    manifest = build_business_info_manifest(
        reviewed,
        estimated_unit_cost_usd=0.0015,
    )

    summary = summarize_business_info_manifest(manifest)

    assert summary["dry_run_only"] is True
    assert summary["api_tasks_submitted"] == 0
    assert summary["planned_tasks"] == 201
    assert summary["planned_post_batches"] == 3
    assert summary["estimated_total_cost_usd"] == 0.3015


def test_build_business_info_manifest_rejects_invalid_cid() -> None:
    reviewed = pd.DataFrame(
        [
            {
                "clinic_key": "google:cid:bad",
                "cid": "not-a-cid",
                "requested_locations": "Malone_NY_S",
                "market_assignment_status": "local_finder_only_unlocated",
                "eligibility_review_status": "needs_geography",
            }
        ]
    )

    try:
        build_business_info_manifest(reviewed)
    except ValueError as error:
        assert "invalid cid" in str(error)
    else:
        raise AssertionError("Expected invalid CID to fail")
