"""Parse audited Google Reviews results with location-level provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from medical_ratings.parsing import parse_reviews_payload


REQUIRED_AUDIT_COLUMNS = {
    "task_tag",
    "task_id",
    "final_physical_location_id",
    "clinic_key",
    "cid",
    "identifier_type",
    "identifier_value",
    "requested_location",
    "item_count",
    "completeness_status",
    "needs_depth_followup",
    "requires_manual_review",
}
REQUIRED_RESULT_LOG_COLUMNS = {
    "task_tag",
    "task_id",
    "download_status",
    "retrieved_at_utc",
}
ACCEPTED_COMPLETENESS_STATUSES = {
    "complete_within_reported_count",
    "empty_result",
    "capped_at_api_limit",
}
DOWNLOADED_STATUSES = {"downloaded", "downloaded_empty"}


def _as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    normalized = series.astype("string").str.strip().str.lower()
    invalid = normalized.notna() & ~normalized.isin({"true", "false", "1", "0"})
    if invalid.any():
        raise ValueError("Boolean audit column contains invalid values")
    return normalized.isin({"true", "1"})


def prepare_parse_plan(
    audit: pd.DataFrame,
    result_log: pd.DataFrame,
    *,
    expected_task_count: int,
) -> pd.DataFrame:
    """Validate and combine one audit and retrieval record per task."""

    missing_audit = REQUIRED_AUDIT_COLUMNS - set(audit.columns)
    if missing_audit:
        raise KeyError(f"Review audit is missing columns: {sorted(missing_audit)}")
    missing_log = REQUIRED_RESULT_LOG_COLUMNS - set(result_log.columns)
    if missing_log:
        raise KeyError(f"Review result log is missing columns: {sorted(missing_log)}")
    if len(audit) != expected_task_count:
        raise ValueError(
            f"Expected {expected_task_count} audited tasks, found {len(audit)}"
        )
    for column in ("task_tag", "task_id", "clinic_key"):
        values = audit[column].astype("string").str.strip()
        if values.isna().any() or values.eq("").any():
            raise ValueError(f"Review audit contains blank {column} values")
        if audit[column].duplicated().any():
            raise ValueError(f"Review audit contains duplicate {column} values")

    observed_statuses = set(audit["completeness_status"].astype(str))
    unexpected = observed_statuses - ACCEPTED_COMPLETENESS_STATUSES
    if unexpected:
        raise ValueError(
            "Review audit contains unresolved completeness statuses: "
            f"{sorted(unexpected)}"
        )
    if _as_bool(audit["needs_depth_followup"]).any():
        raise ValueError("Review audit still contains depth follow-up tasks")
    if _as_bool(audit["requires_manual_review"]).any():
        raise ValueError("Review audit still contains manual-review tasks")

    item_count = pd.to_numeric(audit["item_count"], errors="coerce")
    if item_count.isna().any() or item_count.lt(0).any():
        raise ValueError("Review audit contains invalid item counts")
    prepared_audit = audit.copy()
    prepared_audit["item_count"] = item_count.astype(int)
    empty = prepared_audit["completeness_status"].eq("empty_result")
    if prepared_audit.loc[empty, "item_count"].ne(0).any():
        raise ValueError("Empty-result tasks must contain zero review items")
    if prepared_audit.loc[~empty, "item_count"].eq(0).any():
        raise ValueError("Non-empty tasks must contain at least one review item")

    downloaded = (
        result_log.loc[result_log["download_status"].isin(DOWNLOADED_STATUSES)]
        .drop_duplicates("task_tag", keep="last")
        .copy()
    )
    if len(downloaded) != expected_task_count:
        raise ValueError(
            f"Expected {expected_task_count} downloaded tasks, found {len(downloaded)}"
        )
    duplicate_tags = downloaded["task_tag"].duplicated().any()
    duplicate_ids = downloaded["task_id"].duplicated().any()
    if duplicate_tags or duplicate_ids:
        raise ValueError("Review result log contains duplicate task identities")

    log_columns = [
        "task_tag",
        "task_id",
        "retrieved_at_utc",
        "download_status",
    ]
    if "item_count" in downloaded.columns:
        log_columns.append("item_count")
        downloaded = downloaded.rename(columns={"item_count": "logged_item_count"})
        log_columns[-1] = "logged_item_count"
    plan = prepared_audit.merge(
        downloaded[log_columns],
        on=["task_tag", "task_id"],
        how="left",
        validate="one_to_one",
    )
    if plan["retrieved_at_utc"].isna().any():
        raise ValueError("Some audited tasks have no matching downloaded result log")
    if "logged_item_count" in plan.columns:
        logged_count = pd.to_numeric(plan["logged_item_count"], errors="coerce")
        comparable = logged_count.notna()
        if not logged_count.loc[comparable].astype(int).eq(
            plan.loc[comparable, "item_count"]
        ).all():
            raise ValueError("Audit and result log item counts do not match")
    return plan


def parse_audited_review_results(
    audit: pd.DataFrame,
    result_log: pd.DataFrame,
    raw_directory: Path,
    *,
    expected_task_count: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse all review rows and retain zero-review locations separately."""

    plan = prepare_parse_plan(
        audit,
        result_log,
        expected_task_count=expected_task_count,
    )
    records: list[dict[str, Any]] = []
    zero_review_rows: list[dict[str, Any]] = []
    for row in plan.to_dict(orient="records"):
        task_id = str(row["task_id"])
        raw_path = raw_directory / f"{task_id}.json"
        if not raw_path.is_file():
            raise FileNotFoundError(f"Missing raw review result: {raw_path}")
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError(f"Raw review result must be a JSON object: {raw_path}")
        parsed = parse_reviews_payload(
            payload,
            task_id=task_id,
            requested_location=str(row["requested_location"]),
            retrieved_at_utc=str(row["retrieved_at_utc"]),
        )
        expected_items = int(row["item_count"])
        if len(parsed) != expected_items:
            raise ValueError(
                f"Parsed item count mismatch for {task_id}: "
                f"parsed={len(parsed)}, expected={expected_items}"
            )
        if expected_items == 0:
            zero_review_rows.append(
                {
                    "task_tag": row["task_tag"],
                    "task_id": task_id,
                    "final_physical_location_id": row[
                        "final_physical_location_id"
                    ],
                    "clinic_key": row["clinic_key"],
                    "cid": row["cid"],
                    "identifier_type": row["identifier_type"],
                    "identifier_value": row["identifier_value"],
                    "requested_location": row["requested_location"],
                    "review_observation_status": "zero_reviews_observed",
                    "outcome_profile_key": row.get("outcome_profile_key"),
                    "competition_location_id": row.get(
                        "competition_location_id",
                        row["final_physical_location_id"],
                    ),
                    "address_merge_sensitivity_location_id": row.get(
                        "address_merge_sensitivity_location_id"
                    ),
                }
            )
            continue

        expected_identifier_type = str(row["identifier_type"])
        expected_identifier_value = str(row["identifier_value"])
        expected_cid = str(row["cid"])
        for record in parsed:
            observed_identifier = record.get(expected_identifier_type)
            if str(observed_identifier) != expected_identifier_value:
                raise ValueError(
                    f"Parsed business identifier mismatch for {task_id}"
                )
            observed_cid = record.get("cid")
            if observed_cid is not None and str(observed_cid) != expected_cid:
                raise ValueError(f"Parsed CID mismatch for {task_id}")
            records.append(
                {
                    "task_tag": row["task_tag"],
                    "final_physical_location_id": row[
                        "final_physical_location_id"
                    ],
                    "clinic_key": row["clinic_key"],
                    "outcome_profile_key": row.get(
                        "outcome_profile_key", row["clinic_key"]
                    ),
                    "competition_location_id": row.get(
                        "competition_location_id",
                        row["final_physical_location_id"],
                    ),
                    "address_merge_sensitivity_location_id": row.get(
                        "address_merge_sensitivity_location_id"
                    ),
                    "review_coverage_status": row["completeness_status"],
                    "left_censored_at_api_limit": (
                        row["completeness_status"] == "capped_at_api_limit"
                    ),
                    "submitted_identifier_type": expected_identifier_type,
                    "submitted_identifier_value": expected_identifier_value,
                    **record,
                }
            )

    reviews = pd.DataFrame.from_records(records)
    zero_reviews = pd.DataFrame.from_records(zero_review_rows)
    if reviews.empty:
        raise ValueError("Downloaded review tasks contain no review rows")
    review_id = reviews["review_id"].astype("string").str.strip()
    if review_id.isna().any() or review_id.eq("").any():
        raise ValueError("Parsed reviews contain missing review_id values")
    if review_id.duplicated().any():
        raise ValueError("Parsed reviews contain duplicate review_id values")
    if reviews["final_physical_location_id"].isna().any():
        raise ValueError("Parsed reviews contain missing final location IDs")
    return reviews, zero_reviews


def summarize_parsed_reviews(
    reviews: pd.DataFrame,
    zero_reviews: pd.DataFrame,
    *,
    input_tasks: int,
    output_path: Path,
    zero_review_output: Path,
    summary_output: Path,
) -> dict[str, Any]:
    """Summarize parsed reviews without filtering any observation years."""

    timestamps = pd.to_datetime(
        reviews["review_timestamp_utc"], errors="coerce", utc=True
    )
    ratings = pd.to_numeric(reviews["rating_value"], errors="coerce")
    valid_rating = ratings.between(1, 5)
    years = timestamps.dt.year.dropna().astype(int)
    return {
        "input_tasks": int(input_tasks),
        "tasks_with_reviews": int(reviews["task_id"].nunique()),
        "zero_review_locations": len(zero_reviews),
        "parsed_review_rows": len(reviews),
        "unique_review_id": int(reviews["review_id"].nunique()),
        "unique_physical_locations_with_reviews": int(
            reviews["final_physical_location_id"].nunique()
        ),
        "unique_outcome_profiles_with_reviews": int(
            reviews.get("outcome_profile_key", reviews["clinic_key"]).nunique()
        ),
        "left_censored_outcome_profiles": int(
            reviews.loc[
                reviews.get(
                    "left_censored_at_api_limit",
                    pd.Series(False, index=reviews.index),
                ).fillna(False),
                "clinic_key",
            ].nunique()
        ),
        "review_rows_by_market": {
            str(key): int(value)
            for key, value in reviews["requested_location"]
            .value_counts()
            .sort_index()
            .items()
        },
        "zero_review_locations_by_market": {
            str(key): int(value)
            for key, value in zero_reviews["requested_location"]
            .value_counts()
            .sort_index()
            .items()
        },
        "valid_review_timestamp": int(timestamps.notna().sum()),
        "invalid_review_timestamp": int(timestamps.isna().sum()),
        "valid_rating": int(valid_rating.sum()),
        "invalid_rating": int((~valid_rating).sum()),
        "review_year_counts": {
            str(key): int(value)
            for key, value in years.value_counts().sort_index().items()
        },
        "owner_answer_present": int(reviews["owner_answer"].notna().sum()),
        "output": str(output_path),
        "zero_review_output": str(zero_review_output),
        "summary_output": str(summary_output),
    }
