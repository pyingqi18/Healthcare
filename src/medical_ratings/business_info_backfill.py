"""Plan exact-CID Google Business Info tasks for unresolved candidates."""

from __future__ import annotations

import math

import pandas as pd


REQUIRED_COLUMNS = {
    "clinic_key",
    "cid",
    "requested_locations",
    "market_assignment_status",
    "eligibility_review_status",
}


def build_business_info_manifest(
    reviewed_candidates: pd.DataFrame,
    *,
    location_code: int = 2840,
    language_code: str = "en",
    priority: int = 1,
    estimated_unit_cost_usd: float = 0.0015,
) -> pd.DataFrame:
    """Return one dry-run Business Info task per unresolved Google CID."""

    missing = REQUIRED_COLUMNS - set(reviewed_candidates.columns)
    if missing:
        raise KeyError(f"Reviewed candidates are missing columns: {sorted(missing)}")
    if reviewed_candidates.empty:
        raise ValueError("Reviewed candidate table is empty")
    if priority not in {1, 2}:
        raise ValueError("priority must be 1 or 2")
    if int(location_code) <= 0:
        raise ValueError("location_code must be positive")
    if float(estimated_unit_cost_usd) < 0:
        raise ValueError("estimated_unit_cost_usd cannot be negative")

    unresolved = reviewed_candidates.loc[
        reviewed_candidates["eligibility_review_status"].eq("needs_geography")
    ].copy()
    if unresolved.empty:
        raise ValueError("No needs_geography candidates were found")
    if unresolved["clinic_key"].isna().any() or unresolved["cid"].isna().any():
        raise ValueError("Unresolved candidates contain missing clinic_key or cid")
    if unresolved["clinic_key"].duplicated().any():
        raise ValueError("Unresolved candidates contain duplicate clinic_key values")

    unresolved["cid"] = unresolved["cid"].astype("string").str.strip()
    invalid_cid = ~unresolved["cid"].str.fullmatch(r"\d+")
    if invalid_cid.any():
        examples = unresolved.loc[invalid_cid, "cid"].head(3).tolist()
        raise ValueError(f"Unresolved candidates contain invalid cid values: {examples}")

    manifest = unresolved[
        [
            "clinic_key",
            "cid",
            "requested_locations",
            "market_assignment_status",
        ]
    ].rename(columns={"market_assignment_status": "previous_geography_status"})
    manifest.insert(0, "task_tag", "business_info:cid:" + manifest["cid"])
    manifest["query"] = "cid:" + manifest["cid"]
    manifest["location_code"] = int(location_code)
    manifest["language_code"] = str(language_code)
    manifest["priority"] = int(priority)
    manifest["estimated_unit_cost_usd"] = float(estimated_unit_cost_usd)
    manifest = manifest.sort_values("cid", kind="stable").reset_index(drop=True)

    if manifest["task_tag"].str.len().gt(255).any():
        raise ValueError("Generated task_tag exceeds 255 characters")
    if not manifest["task_tag"].is_unique:
        raise ValueError("Generated task_tag values are not unique")
    return manifest


def summarize_business_info_manifest(
    manifest: pd.DataFrame,
    *,
    maximum_tasks_per_post: int = 100,
) -> dict[str, object]:
    """Summarize task volume, batches, provenance, and estimated cost."""

    if maximum_tasks_per_post < 1:
        raise ValueError("maximum_tasks_per_post must be positive")
    required = {
        "task_tag",
        "cid",
        "previous_geography_status",
        "estimated_unit_cost_usd",
    }
    missing = required - set(manifest.columns)
    if missing:
        raise KeyError(f"Manifest is missing columns: {sorted(missing)}")
    return {
        "dry_run_only": True,
        "api_tasks_submitted": 0,
        "planned_tasks": len(manifest),
        "unique_task_tags": int(manifest["task_tag"].nunique()),
        "unique_cid": int(manifest["cid"].nunique()),
        "maximum_tasks_per_post": int(maximum_tasks_per_post),
        "planned_post_batches": int(
            math.ceil(len(manifest) / maximum_tasks_per_post)
        ),
        "estimated_total_cost_usd": round(
            float(manifest["estimated_unit_cost_usd"].sum()),
            4,
        ),
        "tasks_by_previous_geography_status": {
            str(key): int(value)
            for key, value in manifest["previous_geography_status"]
            .value_counts()
            .sort_index()
            .items()
        },
    }
