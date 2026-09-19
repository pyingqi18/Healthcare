"""Shared validation helpers for configuration-driven paid scrape runs."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def paid_confirmation_text(task_kind: str, task_count: int) -> str:
    """Return the exact confirmation text for the tasks still to submit."""

    normalized_kind = str(task_kind).strip().upper()
    if not normalized_kind or not normalized_kind.replace("_", "").isalnum():
        raise ValueError("task_kind must contain only letters, numbers, or underscores")
    if task_count < 0:
        raise ValueError("task_count cannot be negative")
    return f"SUBMIT_{int(task_count)}_PAID_{normalized_kind}_TASKS"


def paid_request_confirmation_text(request_kind: str, request_count: int) -> str:
    """Return exact confirmation text for live paid API requests."""

    normalized_kind = str(request_kind).strip().upper()
    if not normalized_kind or not normalized_kind.replace("_", "").isalnum():
        raise ValueError(
            "request_kind must contain only letters, numbers, or underscores"
        )
    if request_count < 0:
        raise ValueError("request_count cannot be negative")
    return f"SUBMIT_{int(request_count)}_PAID_{normalized_kind}_REQUESTS"


def submitted_task_rows(
    task_log: pd.DataFrame,
    *,
    required_columns: Iterable[str],
    tag_column: str = "task_tag",
) -> pd.DataFrame:
    """Return one latest row per successfully submitted task tag."""

    required = set(required_columns) | {tag_column, "submission_status"}
    missing = required - set(task_log.columns)
    if missing:
        raise KeyError(f"Task log is missing columns: {sorted(missing)}")

    submitted = (
        task_log.loc[task_log["submission_status"].eq("submitted")]
        .drop_duplicates(tag_column, keep="last")
        .copy()
    )
    if submitted.empty:
        raise ValueError("Task log contains no submitted tasks")
    tags = submitted[tag_column].astype("string").str.strip()
    if tags.isna().any() or tags.eq("").any():
        raise ValueError("Submitted task log contains blank task tags")
    if tags.duplicated().any():
        raise ValueError("Submitted task tags are not unique")
    submitted[tag_column] = tags
    return submitted.reset_index(drop=True)


def expected_task_count(frame: pd.DataFrame, *, tag_column: str = "task_tag") -> int:
    """Derive a positive task count from unique, nonblank task tags."""

    if tag_column not in frame.columns:
        raise KeyError(f"Task data is missing {tag_column}")
    tags = frame[tag_column].astype("string").str.strip()
    if tags.isna().any() or tags.eq("").any():
        raise ValueError("Task data contains blank task tags")
    count = int(tags.nunique())
    if count < 1:
        raise ValueError("Task data contains no tasks")
    return count
