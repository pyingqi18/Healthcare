"""Offline tests for full-run Google Reviews result auditing."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from medical_ratings.review_result_audit import (
    audit_downloaded_review_results,
    audit_review_payload,
    summarize_review_audit,
)


def make_task_log() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_tag": f"reviews:cid:{cid}",
                "task_id": f"task-{cid}",
                "final_physical_location_id": f"location:{cid}",
                "clinic_key": f"google:cid:{cid}",
                "cid": cid,
                "place_id": f"place-{cid}",
                "identifier_type": "place_id",
                "identifier_value": f"place-{cid}",
                "requested_location": market,
                "location_code": location_code,
                "language_code": "en",
                "planned_depth": 20,
                "submission_status": "submitted",
            }
            for cid, market, location_code in (
                ("1", "Malone_NY_S", 1023114),
                ("2", "Syracuse_NY_M", 1023416),
            )
        ]
    )


def make_payload(
    cid: str,
    location_code: int,
    *,
    reviews_count: int,
    review_ids: list[str | None],
) -> dict[str, object]:
    return {
        "status_code": 20000,
        "tasks": [
            {
                "id": f"task-{cid}",
                "status_code": 20000,
                "data": {"tag": f"reviews:cid:{cid}"},
                "result": [
                    {
                        "place_id": f"place-{cid}",
                        "location_code": location_code,
                        "reviews_count": reviews_count,
                        "items": [
                            {"review_id": review_id}
                            for review_id in review_ids
                        ],
                    }
                ],
            }
        ],
    }


def test_audit_payload_flags_depth_followup_and_missing_ids() -> None:
    payload = make_payload(
        "1",
        1023114,
        reviews_count=35,
        review_ids=[*(f"review-{i}" for i in range(19)), None],
    )

    summary, review_ids = audit_review_payload(
        payload,
        expected_task_id="task-1",
        expected_task_tag="reviews:cid:1",
        expected_identifier_type="place_id",
        expected_identifier_value="place-1",
        expected_location_code=1023114,
        planned_depth=20,
    )

    assert summary["item_count"] == 20
    assert summary["missing_review_id"] == 1
    assert summary["completeness_status"] == "needs_depth_followup"
    assert len(review_ids) == 19


def test_audit_all_raw_files_and_summarize_global_duplicates(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    first = make_payload(
        "1",
        1023114,
        reviews_count=2,
        review_ids=["shared-review", "review-1"],
    )
    second = make_payload(
        "2",
        1023416,
        reviews_count=2,
        review_ids=["shared-review", "review-2"],
    )
    (raw / "task-1.json").write_text(json.dumps(first), encoding="utf-8")
    (raw / "task-2.json").write_text(json.dumps(second), encoding="utf-8")

    audit, review_ids = audit_downloaded_review_results(
        make_task_log(),
        raw,
        expected_task_count=2,
    )
    summary = summarize_review_audit(
        audit,
        review_ids,
        raw_json_files=2,
        audit_output=tmp_path / "audit.csv",
        summary_output=tmp_path / "summary.json",
    )

    assert len(audit) == 2
    assert summary["returned_review_rows"] == 4
    assert summary["unique_review_id"] == 3
    assert summary["duplicate_review_id_count"] == 1
    assert summary["repeated_review_observations"] == 1
    assert summary["tasks_needing_depth_followup"] == 0
    assert summary["tasks_requiring_manual_review"] == 0


def test_audit_rejects_wrong_business_identifier() -> None:
    payload = make_payload(
        "1",
        1023114,
        reviews_count=1,
        review_ids=["review-1"],
    )
    payload["tasks"][0]["result"][0]["place_id"] = "wrong-place"

    with pytest.raises(ValueError, match="identifier"):
        audit_review_payload(
            payload,
            expected_task_id="task-1",
            expected_task_tag="reviews:cid:1",
            expected_identifier_type="place_id",
            expected_identifier_value="place-1",
            expected_location_code=1023114,
            planned_depth=20,
        )
