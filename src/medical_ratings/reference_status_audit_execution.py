"""Validate and resume the targeted historical-reference status audit."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from medical_ratings.scrape_safety import submitted_task_rows


REQUIRED_MANIFEST_COLUMNS = {
    "task_tag",
    "plan_type",
    "market",
    "reference_key",
    "query",
    "location_code",
    "language_code",
    "depth",
    "priority",
    "estimated_cost_usd",
    "included_in_main_discovery_pipeline",
    "planning_only",
    "execution_enabled",
}


def _clean(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip()


def _boolean(values: pd.Series, label: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False).astype(bool)
    normalized = _clean(values).str.casefold()
    invalid = set(normalized.dropna()) - {"true", "false", "1", "0"}
    if invalid:
        raise ValueError(f"{label} contains invalid booleans: {sorted(invalid)}")
    return normalized.isin({"true", "1"})


def validate_reference_status_audit_manifest(
    manifest: pd.DataFrame,
    plan_summary: Mapping[str, Any],
) -> pd.DataFrame:
    """Validate the exact planning-only audit scope before paid submission."""

    missing = REQUIRED_MANIFEST_COLUMNS - set(manifest.columns)
    if missing:
        raise KeyError(f"Reference-status manifest is missing: {sorted(missing)}")
    if plan_summary.get("analysis_status") != (
        "post_adjudication_gap_closure_planning_only"
    ):
        raise ValueError("Plan summary is not the post-adjudication completion plan")
    if plan_summary.get("planning_only") is not True:
        raise ValueError("Plan summary must retain planning_only=true")

    expected_count = int(plan_summary.get("reference_status_audit_tasks", 0))
    expected_markets_raw = plan_summary.get("reference_status_audit_markets")
    if expected_count < 1:
        raise ValueError("Plan summary contains no reference-status audit tasks")
    if not isinstance(expected_markets_raw, list) or not expected_markets_raw:
        raise ValueError("Plan summary contains no reference-status audit markets")
    expected_markets = {str(value).strip() for value in expected_markets_raw}
    if len(expected_markets) != len(expected_markets_raw):
        raise ValueError("Plan summary contains duplicate audit markets")

    result = manifest.copy()
    for column in ("task_tag", "market", "reference_key", "query", "plan_type"):
        result[column] = _clean(result[column])
        if result[column].isna().any() or result[column].eq("").any():
            raise ValueError(f"Reference-status manifest has blank {column}")
    if len(result) != expected_count:
        raise ValueError(
            "Reference-status manifest task count differs from the frozen summary"
        )
    if not result["task_tag"].is_unique:
        raise ValueError("Reference-status task tags must be unique")
    if not result["reference_key"].is_unique:
        raise ValueError("Each historical reference may appear only once")
    if set(result["market"]) != expected_markets:
        raise ValueError("Reference-status markets differ from the frozen summary")
    if not result["task_tag"].str.startswith("reference_status_audit:").all():
        raise ValueError("Reference-status manifest contains an unexpected task tag")
    if result["task_tag"].str.len().gt(255).any():
        raise ValueError("Reference-status task tag exceeds 255 characters")
    if set(result["plan_type"]) != {"historical_reference_status_audit"}:
        raise ValueError("Reference-status manifest contains another plan type")

    included = _boolean(
        result["included_in_main_discovery_pipeline"],
        "included_in_main_discovery_pipeline",
    )
    planning = _boolean(result["planning_only"], "planning_only")
    execution = _boolean(result["execution_enabled"], "execution_enabled")
    if included.any():
        raise ValueError("Historical status queries cannot enter main discovery")
    if not planning.all() or execution.any():
        raise ValueError("Manifest no longer matches its frozen planning state")
    if not pd.to_numeric(result["depth"], errors="raise").eq(100).all():
        raise ValueError("Reference-status queries must retain depth 100")
    if not pd.to_numeric(result["priority"], errors="raise").eq(1).all():
        raise ValueError("Reference-status queries must retain priority 1")
    if pd.to_numeric(result["location_code"], errors="raise").le(0).any():
        raise ValueError("Reference-status location codes must be positive")

    expected_cost = float(
        plan_summary.get("reference_status_audit_estimated_cost_usd", -1)
    )
    observed_cost = float(
        pd.to_numeric(result["estimated_cost_usd"], errors="raise").sum()
    )
    if expected_cost < 0 or not math.isclose(
        observed_cost, expected_cost, rel_tol=0, abs_tol=1e-9
    ):
        raise ValueError("Reference-status manifest cost differs from the plan summary")
    result["included_in_main_discovery_pipeline"] = included
    result["planning_only"] = planning
    result["execution_enabled"] = execution
    return result


def submitted_reference_status_tasks(
    task_log: pd.DataFrame,
    manifest: pd.DataFrame,
) -> pd.DataFrame:
    """Return submitted audit tasks after checking tags and identity fields."""

    submitted = submitted_task_rows(
        task_log,
        required_columns={"task_id", "market", "reference_key", "query"},
    )
    expected = manifest.set_index("task_tag")
    unexpected = set(submitted["task_tag"]) - set(expected.index)
    if unexpected:
        raise ValueError(
            f"Reference-status task log contains unexpected tags: {sorted(unexpected)}"
        )
    for row in submitted.itertuples(index=False):
        planned = expected.loc[str(row.task_tag)]
        for column in ("market", "reference_key", "query"):
            if str(getattr(row, column)).strip() != str(planned[column]).strip():
                raise ValueError(
                    f"Reference-status task log changed {column}: {row.task_tag}"
                )
    task_ids = _clean(submitted["task_id"])
    if task_ids.isna().any() or task_ids.eq("").any() or task_ids.duplicated().any():
        raise ValueError("Submitted reference-status task IDs must be unique and nonblank")
    submitted["task_id"] = task_ids
    return submitted


def pending_reference_status_tasks(
    submitted: pd.DataFrame,
    raw_directory: Path,
) -> pd.DataFrame:
    """Return submitted tasks that do not yet have a saved raw response."""

    saved = {path.stem for path in raw_directory.glob("*.json")}
    return submitted.loc[~submitted["task_id"].isin(saved)].copy()
