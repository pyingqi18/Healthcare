"""Consolidate repeated clinic-search observations by Google CID."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from medical_ratings.candidate_audit import _zip_market_lookup
from medical_ratings.identifiers import normalize_zip


REQUIRED_COLUMNS = {
    "cid",
    "place_id",
    "source_api",
    "task_id",
    "task_tag",
    "query",
    "requested_location",
    "title",
    "zip",
    "category",
    "address",
    "latitude",
    "longitude",
    "phone",
    "domain",
    "url",
    "rating_value",
    "votes_count",
    "rank_absolute",
    "result_datetime_utc",
}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return not isinstance(value, str) or bool(value.strip())


def _best_source_row(group: pd.DataFrame, source_api: str) -> Mapping[str, Any] | None:
    source = group.loc[group["source_api"].eq(source_api)].copy()
    if source.empty:
        return None

    completeness_fields = [
        "place_id",
        "title",
        "zip",
        "category",
        "address",
        "latitude",
        "longitude",
        "phone",
        "domain",
        "url",
        "rating_value",
        "votes_count",
    ]
    source["_completeness"] = source[completeness_fields].apply(
        lambda row: sum(_has_value(value) for value in row),
        axis=1,
    )
    source["_votes_numeric"] = pd.to_numeric(
        source["votes_count"], errors="coerce"
    ).fillna(-1)
    source["_rank_numeric"] = pd.to_numeric(
        source["rank_absolute"], errors="coerce"
    ).fillna(float("inf"))
    source = source.sort_values(
        ["_completeness", "_votes_numeric", "_rank_numeric", "task_tag"],
        ascending=[False, False, True, True],
        kind="stable",
    )
    return source.iloc[0].to_dict()


def _prefer(
    primary: Mapping[str, Any] | None,
    secondary: Mapping[str, Any] | None,
    field: str,
) -> Any:
    for row in (primary, secondary):
        if row is not None and _has_value(row.get(field)):
            return row.get(field)
    return None


def build_clinic_candidates(
    observations: pd.DataFrame,
    regions: Mapping[str, Mapping[str, Any]],
) -> pd.DataFrame:
    """Return one auditable candidate row per CID without dropping exclusions."""

    missing = REQUIRED_COLUMNS - set(observations.columns)
    if missing:
        raise KeyError(f"Observations are missing columns: {sorted(missing)}")
    if observations.empty:
        raise ValueError("Observations table is empty")
    if observations["cid"].isna().any():
        raise ValueError("Observations contain missing cid values")

    frame = observations.copy()
    frame["cid_normalized"] = frame["cid"].astype("string").str.strip()
    target_regions = set(frame["requested_location"].dropna().astype(str))
    zip_lookup = _zip_market_lookup(regions, target_regions)

    records: list[dict[str, Any]] = []
    for cid, group in frame.groupby("cid_normalized", sort=True):
        maps_row = _best_source_row(group, "maps")
        finder_row = _best_source_row(group, "local_finder")
        maps_group = group.loc[group["source_api"].eq("maps")].copy()
        observed_zips = sorted(
            {
                value
                for value in maps_group["zip"].map(normalize_zip)
                if value is not None
            }
        )
        if len(observed_zips) > 1:
            raise ValueError(
                f"CID {cid} has multiple Maps ZIP values: {observed_zips}"
            )

        normalized_zip = observed_zips[0] if observed_zips else None
        mapped_location = zip_lookup.get(normalized_zip or "")
        has_maps = maps_row is not None
        has_finder = finder_row is not None
        if mapped_location is not None:
            assignment_status = "eligible_target_zip"
        elif has_maps and normalized_zip is None:
            assignment_status = "maps_missing_zip"
        elif has_maps:
            assignment_status = "outside_target_zip"
        else:
            assignment_status = "local_finder_only_unlocated"

        requested_locations = sorted(
            set(group["requested_location"].dropna().astype(str))
        )
        source_apis = sorted(set(group["source_api"].dropna().astype(str)))
        records.append(
            {
                "clinic_key": f"google:cid:{cid}",
                "cid": str(cid),
                "place_id": _prefer(maps_row, finder_row, "place_id"),
                "title": _prefer(maps_row, finder_row, "title"),
                "category": _prefer(maps_row, finder_row, "category"),
                "address": _prefer(maps_row, finder_row, "address"),
                "zip": normalized_zip,
                "latitude": _prefer(maps_row, finder_row, "latitude"),
                "longitude": _prefer(maps_row, finder_row, "longitude"),
                "phone": _prefer(maps_row, finder_row, "phone"),
                "domain": _prefer(maps_row, finder_row, "domain"),
                "url": _prefer(maps_row, finder_row, "url"),
                "rating_value": _prefer(maps_row, finder_row, "rating_value"),
                "votes_count": _prefer(maps_row, finder_row, "votes_count"),
                "result_datetime_utc": _prefer(
                    maps_row, finder_row, "result_datetime_utc"
                ),
                "mapped_location": mapped_location,
                "market_assignment_status": assignment_status,
                "target_zip_eligible": assignment_status == "eligible_target_zip",
                "found_in_maps": has_maps,
                "found_in_local_finder": has_finder,
                "source_apis": "|".join(source_apis),
                "requested_locations": "|".join(requested_locations),
                "cross_region_search_hit": len(requested_locations) > 1,
                "observation_count": len(group),
                "task_count": int(group["task_tag"].nunique()),
                "query_count": int(group["query"].nunique()),
                "best_maps_rank": (
                    None
                    if maps_group.empty
                    else pd.to_numeric(
                        maps_group["rank_absolute"], errors="coerce"
                    ).min()
                ),
                "best_local_finder_rank": (
                    None
                    if finder_row is None
                    else pd.to_numeric(
                        group.loc[
                            group["source_api"].eq("local_finder"),
                            "rank_absolute",
                        ],
                        errors="coerce",
                    ).min()
                ),
            }
        )

    candidates = pd.DataFrame.from_records(records)
    if candidates["clinic_key"].duplicated().any():
        raise ValueError("Generated clinic candidate keys are not unique")
    return candidates
