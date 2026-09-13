"""Tests for consolidating repeated clinic-search observations."""

import pandas as pd

from medical_ratings.clinic_candidates import build_clinic_candidates


def row(**updates: object) -> dict[str, object]:
    base: dict[str, object] = {
        "cid": "1",
        "place_id": None,
        "source_api": "local_finder",
        "task_id": "task-1",
        "task_tag": "tag-1",
        "query": "dentist",
        "requested_location": "Syracuse_NY_M",
        "title": "Clinic A",
        "zip": None,
        "category": None,
        "address": None,
        "latitude": None,
        "longitude": None,
        "phone": "555-0100",
        "domain": "example.com",
        "url": "https://example.com",
        "rating_value": 4.0,
        "votes_count": 10,
        "rank_absolute": 2,
        "result_datetime_utc": "2026-09-07 20:00:00 +00:00",
    }
    base.update(updates)
    return base


def test_build_clinic_candidates_prefers_maps_and_assigns_zip_market() -> None:
    observations = pd.DataFrame(
        [
            row(),
            row(
                source_api="maps",
                task_id="task-2",
                task_tag="tag-2",
                place_id="place-1",
                zip="13202",
                category="Dentist",
                address="1 Main St",
                latitude=43.0,
                longitude=-76.1,
                phone="555-0199",
                rating_value=4.5,
                votes_count=20,
                rank_absolute=1,
            ),
            row(
                cid="2",
                task_id="task-3",
                task_tag="tag-3",
                requested_location="Malone_NY_S",
                title="Clinic B",
            ),
            row(
                cid="3",
                source_api="maps",
                task_id="task-4",
                task_tag="tag-4",
                requested_location="Malone_NY_S",
                title="Clinic C",
                zip="99999",
                category="Store",
            ),
        ]
    )
    regions = {
        "Malone_NY_S": {"zip_values": [12953]},
        "Syracuse_NY_M": {"zip_ranges": [[13200, 13299]]},
    }

    candidates = build_clinic_candidates(observations, regions).set_index("cid")

    assert len(candidates) == 3
    assert candidates.loc["1", "clinic_key"] == "google:cid:1"
    assert candidates.loc["1", "mapped_location"] == "Syracuse_NY_M"
    assert candidates.loc["1", "market_assignment_status"] == "eligible_target_zip"
    assert candidates.loc["1", "phone"] == "555-0199"
    assert candidates.loc["1", "observation_count"] == 2
    assert candidates.loc["2", "market_assignment_status"] == (
        "local_finder_only_unlocated"
    )
    assert candidates.loc["3", "market_assignment_status"] == "outside_target_zip"


def test_build_clinic_candidates_rejects_conflicting_maps_zips() -> None:
    observations = pd.DataFrame(
        [
            row(source_api="maps", zip="13202"),
            row(source_api="maps", task_id="task-2", task_tag="tag-2", zip="13203"),
        ]
    )
    regions = {"Syracuse_NY_M": {"zip_ranges": [[13200, 13299]]}}

    try:
        build_clinic_candidates(observations, regions)
    except ValueError as error:
        assert "multiple Maps ZIP values" in str(error)
    else:
        raise AssertionError("Expected conflicting Maps ZIP values to fail")
