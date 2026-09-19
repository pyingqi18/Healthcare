"""Tests for dynamic scrape counts and paid-task confirmation text."""

from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.scrape_safety import (
    expected_task_count,
    paid_confirmation_text,
    paid_request_confirmation_text,
    submitted_task_rows,
)


def test_paid_confirmation_uses_remaining_task_count() -> None:
    assert (
        paid_confirmation_text("business_info", 17)
        == "SUBMIT_17_PAID_BUSINESS_INFO_TASKS"
    )
    assert paid_confirmation_text("review", 0) == "SUBMIT_0_PAID_REVIEW_TASKS"


def test_paid_confirmation_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="task_kind"):
        paid_confirmation_text("review tasks", 2)
    with pytest.raises(ValueError, match="negative"):
        paid_confirmation_text("review", -1)


def test_live_request_confirmation_uses_request_unit() -> None:
    assert (
        paid_request_confirmation_text("business_listings", 4)
        == "SUBMIT_4_PAID_BUSINESS_LISTINGS_REQUESTS"
    )


def test_submitted_rows_keep_latest_success_per_tag() -> None:
    log = pd.DataFrame(
        [
            {"task_tag": "a", "task_id": "old", "submission_status": "submitted"},
            {"task_tag": "a", "task_id": "new", "submission_status": "submitted"},
            {"task_tag": "b", "task_id": "failed", "submission_status": "failed"},
        ]
    )

    submitted = submitted_task_rows(log, required_columns={"task_id"})

    assert submitted[["task_tag", "task_id"]].to_dict(orient="records") == [
        {"task_tag": "a", "task_id": "new"}
    ]


def test_expected_count_is_derived_from_tags() -> None:
    frame = pd.DataFrame({"task_tag": ["one", "two", "two"]})

    assert expected_task_count(frame) == 2
