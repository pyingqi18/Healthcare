"""Plan one Google Reviews task per canonical physical location."""

from __future__ import annotations

import math
from typing import Any, Mapping

import pandas as pd


REQUIRED_COLUMNS = {
    "final_physical_location_id",
    "clinic_key",
    "cid",
    "place_id",
    "title",
    "mapped_location",
    "votes_count",
    "final_location_canonical",
}


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _boolean(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no", "", "nan"}:
            return False
        raise ValueError(f"Cannot interpret boolean value: {value}")
    return False if value is None or pd.isna(value) else bool(value)


def _planned_depth(
    votes_count: Any,
    *,
    minimum: int,
    buffer: int,
    maximum: int,
    multiple: int,
) -> tuple[int, str]:
    if votes_count is None or pd.isna(votes_count):
        target = minimum
        source = "missing_votes_minimum"
    else:
        votes = float(votes_count)
        if votes < 0:
            raise ValueError("votes_count cannot be negative")
        target = max(minimum, math.ceil(votes) + buffer)
        source = "votes_count_plus_buffer"
    rounded = int(math.ceil(target / multiple) * multiple)
    return min(maximum, rounded), source


def build_review_collection_manifest(
    locations: pd.DataFrame,
    region_location_codes: Mapping[str, int],
    *,
    language_code: str = "en",
    sort_by: str = "newest",
    depth_minimum: int = 20,
    depth_buffer: int = 50,
    depth_maximum: int = 2000,
    depth_multiple: int = 10,
    standard_cost_per_ten_reviews_usd: float = 0.00075,
) -> pd.DataFrame:
    """Return a dry-run manifest without submitting paid API tasks."""

    missing = REQUIRED_COLUMNS - set(locations.columns)
    if missing:
        raise KeyError(f"Final locations are missing columns: {sorted(missing)}")
    if locations.empty:
        raise ValueError("Final location table is empty")
    if depth_minimum < 1 or depth_maximum > 4490:
        raise ValueError("Review depth bounds must remain within 1 to 4490")
    if depth_minimum > depth_maximum:
        raise ValueError("Review depth minimum exceeds maximum")
    if depth_buffer < 0 or depth_multiple < 1:
        raise ValueError("Review depth buffer and multiple must be valid")
    if depth_minimum % depth_multiple or depth_maximum % depth_multiple:
        raise ValueError("Review depth bounds must be multiples of depth_multiple")
    if standard_cost_per_ten_reviews_usd < 0:
        raise ValueError("Review price cannot be negative")
    if sort_by not in {"newest", "highest_rating", "lowest_rating", "relevant"}:
        raise ValueError("Invalid review sort order")

    frame = locations.copy()
    frame["final_physical_location_id"] = frame[
        "final_physical_location_id"
    ].map(_text)
    frame["clinic_key"] = frame["clinic_key"].map(_text)
    frame["cid"] = frame["cid"].map(_text)
    frame["place_id"] = frame["place_id"].map(_text)
    if frame["final_physical_location_id"].eq("").any():
        raise ValueError("Final locations contain blank identifiers")
    if frame["final_physical_location_id"].duplicated().any():
        raise ValueError("Final locations contain duplicate identifiers")
    if not frame["final_location_canonical"].map(_boolean).all():
        raise ValueError("Every final-location row must be canonical")

    unknown_markets = sorted(
        set(frame["mapped_location"].map(_text)) - set(region_location_codes)
    )
    if unknown_markets:
        raise ValueError(f"Missing region location codes: {unknown_markets}")
    if frame["cid"].eq("").any():
        raise ValueError("Final locations contain blank CID values")

    records: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        place_id = _text(row.place_id)
        cid = _text(row.cid)
        if place_id:
            identifier_type = "place_id"
            identifier_value = place_id
        else:
            identifier_type = "cid"
            identifier_value = cid
        depth, depth_source = _planned_depth(
            row.votes_count,
            minimum=depth_minimum,
            buffer=depth_buffer,
            maximum=depth_maximum,
            multiple=depth_multiple,
        )
        records.append(
            {
                "task_tag": f"reviews:cid:{cid}",
                "final_physical_location_id": row.final_physical_location_id,
                "clinic_key": row.clinic_key,
                "cid": cid,
                "place_id": place_id or None,
                "title": row.title,
                "requested_location": row.mapped_location,
                "identifier_type": identifier_type,
                "identifier_value": identifier_value,
                "location_code": int(region_location_codes[row.mapped_location]),
                "language_code": language_code,
                "sort_by": sort_by,
                "reported_votes_count": row.votes_count,
                "depth_source": depth_source,
                "planned_depth": depth,
                "depth_capped": (
                    depth == depth_maximum
                    and not pd.isna(row.votes_count)
                    and math.ceil(float(row.votes_count)) + depth_buffer
                    > depth_maximum
                ),
                "estimated_maximum_cost_usd": (
                    depth / 10 * standard_cost_per_ten_reviews_usd
                ),
            }
        )

    manifest = pd.DataFrame.from_records(records).sort_values(
        ["requested_location", "cid"], kind="stable"
    ).reset_index(drop=True)
    if manifest["task_tag"].duplicated().any():
        raise ValueError("Generated review task tags are not unique")
    if manifest["identifier_value"].eq("").any():
        raise ValueError("A review task lacks a business identifier")
    return manifest


def summarize_review_collection_manifest(
    manifest: pd.DataFrame,
    *,
    configured_batch_size: int = 50,
    api_maximum_tasks_per_post: int = 100,
) -> dict[str, object]:
    """Summarize volume, depth, provenance, batches, and maximum cost."""

    required = {
        "task_tag",
        "final_physical_location_id",
        "identifier_type",
        "requested_location",
        "reported_votes_count",
        "planned_depth",
        "depth_capped",
        "estimated_maximum_cost_usd",
    }
    missing = required - set(manifest.columns)
    if missing:
        raise KeyError(f"Review manifest is missing columns: {sorted(missing)}")
    if not 1 <= configured_batch_size <= api_maximum_tasks_per_post:
        raise ValueError("Configured batch size exceeds the API task limit")
    return {
        "dry_run_only": True,
        "api_tasks_submitted": 0,
        "planned_tasks": len(manifest),
        "unique_task_tags": int(manifest["task_tag"].nunique()),
        "unique_physical_locations": int(
            manifest["final_physical_location_id"].nunique()
        ),
        "tasks_with_place_id": int(
            manifest["identifier_type"].eq("place_id").sum()
        ),
        "tasks_using_cid_fallback": int(
            manifest["identifier_type"].eq("cid").sum()
        ),
        "tasks_with_missing_reported_votes": int(
            manifest["reported_votes_count"].isna().sum()
        ),
        "tasks_with_capped_depth": int(manifest["depth_capped"].sum()),
        "total_planned_depth": int(manifest["planned_depth"].sum()),
        "configured_batch_size": int(configured_batch_size),
        "api_maximum_tasks_per_post": int(api_maximum_tasks_per_post),
        "planned_post_batches": int(
            math.ceil(len(manifest) / configured_batch_size)
        ),
        "estimated_maximum_cost_usd": round(
            float(manifest["estimated_maximum_cost_usd"].sum()), 4
        ),
        "tasks_by_market": {
            str(key): int(value)
            for key, value in manifest["requested_location"]
            .value_counts().sort_index().items()
        },
        "planned_depth_by_market": {
            str(key): int(value)
            for key, value in manifest.groupby("requested_location")[
                "planned_depth"
            ].sum().sort_index().items()
        },
    }
