"""Audits for deduplicating and assigning clinic-search candidates."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from medical_ratings.identifiers import normalize_zip


REQUIRED_COLUMNS = {
    "cid",
    "source_api",
    "requested_location",
    "task_tag",
    "query",
    "zip",
    "category",
}


def _region_zip_values(details: Mapping[str, Any]) -> set[str]:
    values = {
        normalize_zip(value)
        for value in details.get("zip_values") or []
    }
    for bounds in details.get("zip_ranges") or []:
        if len(bounds) != 2:
            raise ValueError(f"Invalid ZIP range: {bounds}")
        start, end = (int(bounds[0]), int(bounds[1]))
        values.update(normalize_zip(value) for value in range(start, end + 1))
    return {value for value in values if value is not None}


def _zip_market_lookup(
    regions: Mapping[str, Mapping[str, Any]],
    target_regions: set[str],
) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for region_key in sorted(target_regions):
        details = regions.get(region_key)
        if not isinstance(details, Mapping):
            raise KeyError(f"Unknown region: {region_key}")
        for zip_code in _region_zip_values(details):
            existing = lookup.get(zip_code)
            if existing is not None and existing != region_key:
                raise ValueError(
                    f"ZIP {zip_code} belongs to multiple target regions"
                )
            lookup[zip_code] = region_key
    return lookup


def _set_by_group(
    frame: pd.DataFrame,
    group_column: str,
) -> dict[str, set[str]]:
    return {
        str(key): set(group["cid_normalized"])
        for key, group in frame.groupby(group_column)
    }


def audit_search_candidates(
    observations: pd.DataFrame,
    regions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize identifier overlap, geography, and keyword efficiency."""

    missing = REQUIRED_COLUMNS - set(observations.columns)
    if missing:
        raise KeyError(f"Observations are missing columns: {sorted(missing)}")
    if observations.empty:
        raise ValueError("Observations table is empty")

    frame = observations.copy()
    if frame["cid"].isna().any():
        raise ValueError("Observations contain missing cid values")
    frame["cid_normalized"] = frame["cid"].astype("string").str.strip()
    frame["combination_size"] = frame["query"].astype("string").str.count(r"\+") + 1

    api_sets = _set_by_group(frame, "source_api")
    region_sets = _set_by_group(frame, "requested_location")
    maps_ids = api_sets.get("maps", set())
    finder_ids = api_sets.get("local_finder", set())
    target_regions = set(region_sets)

    singleton_ids = set(frame.loc[frame["combination_size"].eq(1), "cid_normalized"])
    all_ids = set(frame["cid_normalized"])
    keyword_efficiency: dict[str, dict[str, int]] = {
        "all": {
            "tasks": int(frame["task_tag"].nunique()),
            "unique_cid": len(all_ids),
            "singleton_unique_cid": len(singleton_ids),
            "combination_only_unique_cid": len(all_ids - singleton_ids),
        }
    }
    for api_type, group in frame.groupby("source_api"):
        group_all = set(group["cid_normalized"])
        group_single = set(
            group.loc[group["combination_size"].eq(1), "cid_normalized"]
        )
        keyword_efficiency[str(api_type)] = {
            "tasks": int(group["task_tag"].nunique()),
            "unique_cid": len(group_all),
            "singleton_unique_cid": len(group_single),
            "combination_only_unique_cid": len(group_all - group_single),
        }

    region_overlap: dict[str, int] = {}
    region_names = sorted(region_sets)
    for index, left in enumerate(region_names):
        for right in region_names[index + 1 :]:
            region_overlap[f"{left}__and__{right}"] = len(
                region_sets[left] & region_sets[right]
            )

    maps = frame.loc[frame["source_api"].eq("maps")].copy()
    maps["zip_normalized"] = maps["zip"].map(normalize_zip)
    zip_lookup = _zip_market_lookup(regions, target_regions)
    maps["zip_market"] = maps["zip_normalized"].map(zip_lookup)
    maps_by_cid = maps.groupby("cid_normalized", dropna=False)
    maps_with_zip = {
        str(cid)
        for cid, group in maps_by_cid
        if group["zip_normalized"].notna().any()
    }
    maps_in_target_zip = {
        str(cid)
        for cid, group in maps_by_cid
        if group["zip_market"].notna().any()
    }
    maps_multiple_zips = sum(
        group["zip_normalized"].dropna().nunique() > 1
        for _, group in maps_by_cid
    )
    target_zip_counts = {
        str(key): int(value)
        for key, value in (
            maps.dropna(subset=["zip_market"])
            .drop_duplicates(["cid_normalized", "zip_market"])
            ["zip_market"]
            .value_counts()
            .sort_index()
            .items()
        )
    }

    categories = (
        maps["category"]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .value_counts()
        .head(25)
    )

    return {
        "observations": len(frame),
        "unique_cid": len(all_ids),
        "api_identifier_overlap": {
            "maps_unique_cid": len(maps_ids),
            "local_finder_unique_cid": len(finder_ids),
            "both_apis": len(maps_ids & finder_ids),
            "maps_only": len(maps_ids - finder_ids),
            "local_finder_only": len(finder_ids - maps_ids),
        },
        "unique_cid_by_requested_region": {
            key: len(value) for key, value in sorted(region_sets.items())
        },
        "cross_region_overlap": region_overlap,
        "maps_geography": {
            "maps_unique_cid": len(maps_ids),
            "with_zip": len(maps_with_zip),
            "missing_zip": len(maps_ids - maps_with_zip),
            "in_target_zip_scope": len(maps_in_target_zip),
            "outside_target_zip_scope": len(maps_ids - maps_in_target_zip),
            "with_multiple_observed_zips": int(maps_multiple_zips),
            "unique_cid_by_target_zip_market": target_zip_counts,
        },
        "keyword_efficiency": keyword_efficiency,
        "top_maps_categories": {
            str(key): int(value) for key, value in categories.items()
        },
    }
