"""Offline audit helpers for downloaded Google Reviews task results."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


REQUIRED_TASK_COLUMNS = {
    "task_tag",
    "task_id",
    "final_physical_location_id",
    "clinic_key",
    "cid",
    "identifier_type",
    "identifier_value",
    "requested_location",
    "location_code",
    "language_code",
    "planned_depth",
    "submission_status",
}


def _required_text(frame: pd.DataFrame, column: str) -> pd.Series:
    values = frame[column].astype("string").str.strip()
    if values.isna().any() or values.eq("").any():
        raise ValueError(f"Task log contains blank {column} values")
    return values


def prepare_submitted_tasks(
    task_log: pd.DataFrame,
    *,
    expected_task_count: int,
) -> pd.DataFrame:
    """Return one validated successful record per submitted review task."""

    missing = REQUIRED_TASK_COLUMNS - set(task_log.columns)
    if missing:
        raise KeyError(f"Task log is missing columns: {sorted(missing)}")
    submitted = (
        task_log.loc[task_log["submission_status"].eq("submitted")]
        .drop_duplicates("task_tag", keep="last")
        .copy()
    )
    if len(submitted) != expected_task_count:
        raise ValueError(
            f"Expected {expected_task_count} submitted tasks, found {len(submitted)}"
        )

    for column in (
        "task_tag",
        "task_id",
        "final_physical_location_id",
        "clinic_key",
        "cid",
        "identifier_type",
        "identifier_value",
        "requested_location",
        "language_code",
    ):
        submitted[column] = _required_text(submitted, column)
    for column in ("task_tag", "task_id", "final_physical_location_id"):
        if submitted[column].duplicated().any():
            raise ValueError(f"Submitted tasks contain duplicate {column} values")

    identifier_types = set(submitted["identifier_type"])
    if not identifier_types.issubset({"place_id", "cid"}):
        raise ValueError("Submitted tasks contain invalid identifier types")
    planned_depth = pd.to_numeric(submitted["planned_depth"], errors="coerce")
    if planned_depth.isna().any() or not planned_depth.between(1, 4490).all():
        raise ValueError("Submitted tasks contain invalid planned depths")
    submitted["planned_depth"] = planned_depth.astype(int)
    location_code = pd.to_numeric(submitted["location_code"], errors="coerce")
    if location_code.isna().any():
        raise ValueError("Submitted tasks contain invalid location codes")
    submitted["location_code"] = location_code.astype(int)
    return submitted.reset_index(drop=True)


def _integer_or_none(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def audit_review_payload(
    payload: Mapping[str, Any],
    *,
    expected_task_id: str,
    expected_task_tag: str,
    expected_identifier_type: str,
    expected_identifier_value: str,
    expected_location_code: int,
    planned_depth: int,
) -> tuple[dict[str, Any], list[str]]:
    """Validate one raw response and return task and review-ID summaries."""

    tasks = payload.get("tasks") or []
    if len(tasks) != 1 or not isinstance(tasks[0], Mapping):
        raise ValueError(f"Expected one response task, found {len(tasks)}")
    task = tasks[0]
    if str(task.get("id")) != expected_task_id:
        raise ValueError("Response task ID does not match the task log")
    data = task.get("data")
    if not isinstance(data, Mapping) or str(data.get("tag")) != expected_task_tag:
        raise ValueError("Response task tag does not match the task log")

    results = task.get("result")
    if results is None:
        raise ValueError("Raw result is not ready")
    if not isinstance(results, list):
        raise TypeError("Response task result must be a list")

    items: list[Mapping[str, Any]] = []
    identifiers: set[str] = set()
    location_codes: set[int] = set()
    reported_counts: list[int] = []
    for result in results:
        if not isinstance(result, Mapping):
            raise TypeError("Review result block must be a JSON object")
        identifier = result.get(expected_identifier_type)
        if identifier is not None:
            identifiers.add(str(identifier).strip())
        location_code = _integer_or_none(result.get("location_code"))
        if location_code is not None:
            location_codes.add(location_code)
        reviews_count = _integer_or_none(result.get("reviews_count"))
        if reviews_count is not None:
            reported_counts.append(reviews_count)
        result_items = result.get("items") or []
        if not isinstance(result_items, list):
            raise TypeError("Review result items must be a list")
        for item in result_items:
            if not isinstance(item, Mapping):
                raise TypeError("Review item must be a JSON object")
            items.append(item)

    if results and identifiers != {expected_identifier_value}:
        raise ValueError(
            "Review result business identifier does not match the task log"
        )
    if location_codes and location_codes != {expected_location_code}:
        raise ValueError("Review result location code does not match the task log")

    review_ids = [
        str(item["review_id"]).strip()
        for item in items
        if item.get("review_id") is not None and str(item["review_id"]).strip()
    ]
    id_counts = Counter(review_ids)
    duplicate_id_count = sum(count > 1 for count in id_counts.values())
    duplicate_rows = sum(count for count in id_counts.values() if count > 1)
    item_count = len(items)
    business_reviews_count = (
        max(reported_counts) if reported_counts else None
    )
    depth_exhausted = item_count >= planned_depth

    if not results or item_count == 0:
        completeness_status = (
            "unexpected_empty_result"
            if business_reviews_count is not None
            and business_reviews_count > 0
            else "empty_result"
        )
    elif business_reviews_count is None:
        completeness_status = (
            "unknown_count_at_depth_limit"
            if depth_exhausted
            else "unknown_count_below_depth"
        )
    elif business_reviews_count > item_count and depth_exhausted:
        completeness_status = "needs_depth_followup"
    elif business_reviews_count > item_count:
        completeness_status = "short_return_below_depth"
    else:
        completeness_status = "complete_within_reported_count"

    summary = {
        "response_status": payload.get("status_code"),
        "task_status": task.get("status_code"),
        "result_blocks": len(results),
        "item_count": item_count,
        "rows_with_review_id": len(review_ids),
        "missing_review_id": item_count - len(review_ids),
        "unique_review_id": len(id_counts),
        "duplicate_review_id_count_within_task": duplicate_id_count,
        "duplicate_review_rows_within_task": duplicate_rows,
        "business_reviews_count": business_reviews_count,
        "planned_depth": planned_depth,
        "depth_exhausted": depth_exhausted,
        "unreturned_reported_reviews": (
            None
            if business_reviews_count is None
            else max(business_reviews_count - item_count, 0)
        ),
        "completeness_status": completeness_status,
        "needs_depth_followup": completeness_status == "needs_depth_followup",
        "requires_manual_review": completeness_status
        in {
            "unexpected_empty_result",
            "short_return_below_depth",
            "unknown_count_at_depth_limit",
        },
    }
    return summary, review_ids


def audit_downloaded_review_results(
    task_log: pd.DataFrame,
    raw_directory: Path,
    *,
    expected_task_count: int,
) -> tuple[pd.DataFrame, list[str]]:
    """Audit every submitted task directly from its saved raw JSON."""

    submitted = prepare_submitted_tasks(
        task_log,
        expected_task_count=expected_task_count,
    )
    audit_rows: list[dict[str, Any]] = []
    all_review_ids: list[str] = []
    for row in submitted.to_dict(orient="records"):
        task_id = str(row["task_id"])
        raw_path = raw_directory / f"{task_id}.json"
        if not raw_path.is_file():
            raise FileNotFoundError(f"Missing raw review result: {raw_path}")
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError(f"Raw review result must be a JSON object: {raw_path}")
        task_summary, review_ids = audit_review_payload(
            payload,
            expected_task_id=task_id,
            expected_task_tag=str(row["task_tag"]),
            expected_identifier_type=str(row["identifier_type"]),
            expected_identifier_value=str(row["identifier_value"]),
            expected_location_code=int(row["location_code"]),
            planned_depth=int(row["planned_depth"]),
        )
        audit_rows.append(
            {
                "task_tag": row["task_tag"],
                "task_id": task_id,
                "final_physical_location_id": row["final_physical_location_id"],
                "clinic_key": row["clinic_key"],
                "cid": row["cid"],
                "identifier_type": row["identifier_type"],
                "identifier_value": row["identifier_value"],
                "requested_location": row["requested_location"],
                "location_code": row["location_code"],
                "language_code": row["language_code"],
                "raw_response_path": str(raw_path),
                **task_summary,
            }
        )
        all_review_ids.extend(review_ids)

    audit = pd.DataFrame.from_records(audit_rows)
    if len(audit) != expected_task_count:
        raise ValueError(
            f"Expected {expected_task_count} audited tasks, found {len(audit)}"
        )
    return audit, all_review_ids


def summarize_review_audit(
    audit: pd.DataFrame,
    review_ids: list[str],
    *,
    raw_json_files: int,
    audit_output: Path,
    summary_output: Path,
) -> dict[str, Any]:
    """Build a compact full-run summary from task-level audit records."""

    id_counts = Counter(review_ids)
    duplicate_id_count = sum(count > 1 for count in id_counts.values())
    duplicate_rows = sum(count for count in id_counts.values() if count > 1)
    return {
        "submitted_tasks": len(audit),
        "raw_json_files": int(raw_json_files),
        "audited_tasks": len(audit),
        "unique_physical_locations": int(
            audit["final_physical_location_id"].nunique()
        ),
        "tasks_by_market": {
            str(key): int(value)
            for key, value in audit["requested_location"]
            .value_counts()
            .sort_index()
            .items()
        },
        "completeness_status": {
            str(key): int(value)
            for key, value in audit["completeness_status"]
            .value_counts()
            .sort_index()
            .items()
        },
        "planned_depth": int(audit["planned_depth"].sum()),
        "returned_review_rows": int(audit["item_count"].sum()),
        "returned_review_rows_by_market": {
            str(key): int(value)
            for key, value in audit.groupby("requested_location")["item_count"]
            .sum()
            .sort_index()
            .items()
        },
        "rows_with_review_id": len(review_ids),
        "missing_review_id": int(audit["missing_review_id"].sum()),
        "unique_review_id": len(id_counts),
        "duplicate_review_id_count": duplicate_id_count,
        "duplicate_review_rows": duplicate_rows,
        "repeated_review_observations": len(review_ids) - len(id_counts),
        "tasks_needing_depth_followup": int(
            audit["needs_depth_followup"].sum()
        ),
        "tasks_requiring_manual_review": int(
            audit["requires_manual_review"].sum()
        ),
        "unreturned_reported_reviews": int(
            pd.to_numeric(
                audit["unreturned_reported_reviews"], errors="coerce"
            ).fillna(0).sum()
        ),
        "audit_output": str(audit_output),
        "summary_output": str(summary_output),
    }
