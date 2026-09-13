"""Offline tests for audited Google Reviews result parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from medical_ratings.review_result_parsing import (
    parse_audited_review_results,
    prepare_parse_plan,
    summarize_parsed_reviews,
)


def make_audit() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_tag": "reviews:cid:1",
                "task_id": "task-1",
                "final_physical_location_id": "location:1",
                "clinic_key": "google:cid:1",
                "cid": "1",
                "identifier_type": "place_id",
                "identifier_value": "place-1",
                "requested_location": "Malone_NY_S",
                "item_count": 2,
                "completeness_status": "complete_within_reported_count",
                "needs_depth_followup": False,
                "requires_manual_review": False,
            },
            {
                "task_tag": "reviews:cid:2",
                "task_id": "task-2",
                "final_physical_location_id": "location:2",
                "clinic_key": "google:cid:2",
                "cid": "2",
                "identifier_type": "place_id",
                "identifier_value": "place-2",
                "requested_location": "Syracuse_NY_M",
                "item_count": 0,
                "completeness_status": "empty_result",
                "needs_depth_followup": False,
                "requires_manual_review": False,
            },
        ]
    )


def make_result_log() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_tag": "reviews:cid:1",
                "task_id": "task-1",
                "download_status": "downloaded",
                "retrieved_at_utc": "2026-09-10T12:00:00+00:00",
                "item_count": 2,
            },
            {
                "task_tag": "reviews:cid:2",
                "task_id": "task-2",
                "download_status": "downloaded_empty",
                "retrieved_at_utc": "2026-09-10T12:01:00+00:00",
                "item_count": 0,
            },
        ]
    )


def review_payload() -> dict[str, object]:
    return {
        "tasks": [
            {
                "id": "task-1",
                "data": {"tag": "reviews:cid:1"},
                "result": [
                    {
                        "location_code": 1023114,
                        "language_code": "en",
                        "datetime": "2026-09-10 11:50:00 +00:00",
                        "place_id": "place-1",
                        "cid": "1",
                        "title": "Clinic One",
                        "reviews_count": 2,
                        "items": [
                            {
                                "review_id": "review-1",
                                "timestamp": "2025-01-01 10:00:00 +00:00",
                                "rating": {"value": 5, "rating_max": 5},
                                "owner_answer": "Thank you",
                            },
                            {
                                "review_id": "review-2",
                                "timestamp": "2026-01-01 10:00:00 +00:00",
                                "rating": {"value": 4, "rating_max": 5},
                            },
                        ],
                    }
                ],
            }
        ]
    }


def empty_payload() -> dict[str, object]:
    return {
        "tasks": [
            {
                "id": "task-2",
                "data": {"tag": "reviews:cid:2"},
                "result": [
                    {
                        "location_code": 1023416,
                        "place_id": "place-2",
                        "cid": "2",
                        "items": [],
                    }
                ],
            }
        ]
    }


def test_prepare_parse_plan_rejects_unresolved_tasks() -> None:
    audit = make_audit()
    audit.loc[0, "needs_depth_followup"] = True

    with pytest.raises(ValueError, match="follow-up"):
        prepare_parse_plan(
            audit,
            make_result_log(),
            expected_task_count=2,
        )


def test_parse_reviews_and_retain_zero_review_location(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "task-1.json").write_text(
        json.dumps(review_payload()), encoding="utf-8"
    )
    (raw / "task-2.json").write_text(
        json.dumps(empty_payload()), encoding="utf-8"
    )

    reviews, zero_reviews = parse_audited_review_results(
        make_audit(),
        make_result_log(),
        raw,
        expected_task_count=2,
    )

    assert len(reviews) == 2
    assert reviews["review_id"].tolist() == ["review-1", "review-2"]
    assert set(reviews["final_physical_location_id"]) == {"location:1"}
    assert len(zero_reviews) == 1
    assert zero_reviews.iloc[0]["final_physical_location_id"] == "location:2"


def test_parser_rejects_duplicate_review_ids(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    payload = review_payload()
    payload["tasks"][0]["result"][0]["items"][1]["review_id"] = "review-1"
    (raw / "task-1.json").write_text(json.dumps(payload), encoding="utf-8")
    (raw / "task-2.json").write_text(
        json.dumps(empty_payload()), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="duplicate review_id"):
        parse_audited_review_results(
            make_audit(),
            make_result_log(),
            raw,
            expected_task_count=2,
        )


def test_summary_reports_years_ratings_and_zero_review_market(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "task-1.json").write_text(
        json.dumps(review_payload()), encoding="utf-8"
    )
    (raw / "task-2.json").write_text(
        json.dumps(empty_payload()), encoding="utf-8"
    )
    reviews, zero_reviews = parse_audited_review_results(
        make_audit(),
        make_result_log(),
        raw,
        expected_task_count=2,
    )

    summary = summarize_parsed_reviews(
        reviews,
        zero_reviews,
        input_tasks=2,
        output_path=tmp_path / "reviews.csv",
        zero_review_output=tmp_path / "zero.csv",
        summary_output=tmp_path / "summary.json",
    )

    assert summary["parsed_review_rows"] == 2
    assert summary["review_year_counts"] == {"2025": 1, "2026": 1}
    assert summary["valid_rating"] == 2
    assert summary["invalid_rating"] == 0
    assert summary["zero_review_locations_by_market"] == {"Syracuse_NY_M": 1}
