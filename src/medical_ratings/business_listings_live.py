"""Validation and parsing for live Business Listings pilot responses."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_MANIFEST_COLUMNS = {
    "task_tag",
    "market",
    "category_group",
    "categories",
    "category_count",
    "location_coordinate",
    "limit",
    "planning_only",
    "execution_enabled",
}


def business_listings_page_metadata(
    payload: Mapping[str, Any],
    *,
    expected_tag: str,
    requested_offset: int = 0,
) -> dict[str, Any]:
    """Summarize whether one Business Listings response needs another page."""

    tasks = payload.get("tasks") or []
    if len(tasks) != 1 or not isinstance(tasks[0], Mapping):
        raise ValueError("Business Listings payload must contain exactly one task")
    task = tasks[0]
    data = task.get("data") or {}
    if not isinstance(data, Mapping) or str(data.get("tag", "")) != expected_tag:
        raise ValueError("Business Listings payload tag does not match the result log")
    results = task.get("result") or []
    if len(results) != 1 or not isinstance(results[0], Mapping):
        raise ValueError("Business Listings payload must contain exactly one result")
    result = results[0]
    items = result.get("items") or []
    returned_count = len(items)
    reported_count = result.get("count")
    if reported_count is not None and int(reported_count) != returned_count:
        raise ValueError("Business Listings result count does not match items")
    if result.get("total_count") is None:
        raise ValueError("Business Listings result lacks total_count")
    total_count = int(result["total_count"])
    if total_count < returned_count:
        raise ValueError("Business Listings total_count is below returned item count")
    next_token = result.get("offset_token")
    if isinstance(next_token, Mapping):
        next_token = next_token.get("value") or next_token.get("token")
    if next_token is not None:
        next_token = str(next_token).strip() or None
    has_more = total_count > int(requested_offset) + returned_count
    return {
        "total_count": total_count,
        "returned_item_count": returned_count,
        "requested_offset": int(requested_offset),
        "next_offset": int(requested_offset) + returned_count,
        "next_offset_token": next_token,
        "pagination_required": has_more,
        "continuation_available": has_more and (
            next_token is not None or int(requested_offset) + returned_count <= 10000
        ),
    }


def audit_business_listings_page_groups(
    pages: pd.DataFrame,
) -> pd.DataFrame:
    """Audit whether saved page intervals completely cover each category group."""

    required = {
        "market",
        "category_group",
        "total_count",
        "returned_item_count",
        "requested_offset",
    }
    missing = required - set(pages.columns)
    if missing:
        raise KeyError(f"Business Listings pages are missing: {sorted(missing)}")
    if pages.empty:
        raise ValueError("Business Listings page audit is empty")

    records: list[dict[str, Any]] = []
    for (market, category_group), group in pages.groupby(
        ["market", "category_group"], sort=True, dropna=False
    ):
        work = group.copy()
        for column in ("total_count", "returned_item_count", "requested_offset"):
            work[column] = pd.to_numeric(work[column], errors="raise").astype(int)
            if work[column].lt(0).any():
                raise ValueError(f"{column} cannot be negative")
        total_values = sorted(set(work["total_count"].tolist()))
        total_consistent = len(total_values) == 1
        total_count = total_values[0] if total_consistent else max(total_values)
        work = work.sort_values("requested_offset", kind="stable")
        duplicate_offsets = work["requested_offset"].duplicated().any()

        intervals: list[tuple[int, int]] = []
        for row in work.itertuples(index=False):
            start = int(row.requested_offset)
            end = min(total_count, start + int(row.returned_item_count))
            if start < total_count and end > start:
                intervals.append((start, end))
        merged: list[list[int]] = []
        overlap_detected = False
        for start, end in intervals:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                if start < merged[-1][1]:
                    overlap_detected = True
                merged[-1][1] = max(merged[-1][1], end)
        covered = sum(end - start for start, end in merged)
        gap_detected = not (
            len(merged) == 1 and merged[0][0] == 0 and merged[0][1] >= total_count
        )
        complete = (
            total_consistent
            and not duplicate_offsets
            and not overlap_detected
            and not gap_detected
            and covered == total_count
        )
        records.append(
            {
                "market": market,
                "category_group": category_group,
                "reported_total_count": total_count,
                "total_count_consistent": total_consistent,
                "saved_page_count": len(work),
                "saved_offsets": "|".join(
                    str(value) for value in work["requested_offset"].tolist()
                ),
                "saved_items_across_pages": int(work["returned_item_count"].sum()),
                "covered_item_positions": covered,
                "missing_item_positions": max(total_count - covered, 0),
                "duplicate_offsets": bool(duplicate_offsets),
                "overlap_detected": overlap_detected,
                "gap_detected": gap_detected,
                "category_group_complete": complete,
            }
        )
    return pd.DataFrame.from_records(records)


def _manifest_bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{label} must be true or false")


def parse_category_cell(value: object) -> list[str]:
    """Parse and validate the pipe-delimited categories in one manifest row."""

    categories = [part.strip() for part in str(value).split("|")]
    if not 1 <= len(categories) <= 10 or any(not value for value in categories):
        raise ValueError("Manifest categories must contain 1 to 10 names")
    if len(categories) != len(set(categories)):
        raise ValueError("Manifest categories contain duplicates")
    return categories


def validate_pilot_manifest(manifest: pd.DataFrame) -> pd.DataFrame:
    """Validate the frozen four-request pilot manifest."""

    missing = REQUIRED_MANIFEST_COLUMNS - set(manifest.columns)
    if missing:
        raise KeyError(f"Pilot manifest is missing columns: {sorted(missing)}")
    if len(manifest) != 4:
        raise ValueError("Pilot manifest must contain exactly four requests")
    result = manifest.copy()
    tags = result["task_tag"].astype("string").str.strip()
    if tags.isna().any() or tags.eq("").any() or tags.duplicated().any():
        raise ValueError("Pilot manifest task tags must be nonblank and unique")
    result["task_tag"] = tags
    if set(result["market"].astype(str)) != {"Malone_NY_S", "Syracuse_NY_M"}:
        raise ValueError("Pilot manifest must contain Malone and Syracuse only")
    if result.groupby("market").size().to_dict() != {
        "Malone_NY_S": 2,
        "Syracuse_NY_M": 2,
    }:
        raise ValueError("Pilot manifest must contain two requests per market")
    for row in result.itertuples(index=False):
        categories = parse_category_cell(row.categories)
        if len(categories) != int(row.category_count):
            raise ValueError("Manifest category_count does not match categories")
        if int(row.limit) != 1000:
            raise ValueError("Pilot manifest limit must remain 1000")
        if _manifest_bool(row.planning_only, "planning_only") is not True:
            raise ValueError("Pilot manifest must retain planning_only=true")
        if _manifest_bool(row.execution_enabled, "execution_enabled") is not False:
            raise ValueError("Pilot manifest must retain execution_enabled=false")
    return result.reset_index(drop=True)


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def parse_business_listings_payload(
    payload: Mapping[str, Any],
    *,
    expected_tag: str,
    market: str,
    retrieved_at_utc: str,
) -> list[dict[str, Any]]:
    """Flatten one raw live response while preserving stable identities."""

    tasks = payload.get("tasks") or []
    if len(tasks) != 1 or not isinstance(tasks[0], Mapping):
        raise ValueError("Business Listings payload must contain exactly one task")
    task = tasks[0]
    data = task.get("data") or {}
    if not isinstance(data, Mapping) or str(data.get("tag", "")) != expected_tag:
        raise ValueError("Business Listings payload tag does not match the result log")

    records: list[dict[str, Any]] = []
    for result in task.get("result") or []:
        if not isinstance(result, Mapping):
            raise TypeError("Business Listings result must be an object")
        for item in result.get("items") or []:
            if not isinstance(item, Mapping):
                raise TypeError("Business Listings item must be an object")
            if item.get("type") not in {None, "business_listing"}:
                continue
            cid = item.get("cid")
            place_id = item.get("place_id")
            if not cid and not place_id:
                raise ValueError("Business Listings item lacks both cid and place_id")
            address_info = item.get("address_info") or {}
            rating = item.get("rating") or {}
            if not isinstance(address_info, Mapping) or not isinstance(rating, Mapping):
                raise TypeError("Business Listings address_info and rating must be objects")
            records.append(
                {
                    "source_api": "business_listings_live",
                    "task_id": task.get("id"),
                    "task_tag": expected_tag,
                    "requested_location": market,
                    "retrieved_at_utc": retrieved_at_utc,
                    "cid": cid,
                    "place_id": place_id,
                    "feature_id": item.get("feature_id"),
                    "title": item.get("title"),
                    "original_title": item.get("original_title"),
                    "category": item.get("category"),
                    "category_ids_json": _json_text(item.get("category_ids") or []),
                    "additional_categories_json": _json_text(
                        item.get("additional_categories") or []
                    ),
                    "address": item.get("address"),
                    "street_address": address_info.get("address"),
                    "city": address_info.get("city"),
                    "zip": address_info.get("zip"),
                    "region": address_info.get("region"),
                    "country_code": address_info.get("country_code"),
                    "latitude": item.get("latitude"),
                    "longitude": item.get("longitude"),
                    "phone": item.get("phone"),
                    "url": item.get("url"),
                    "domain": item.get("domain"),
                    "is_claimed": item.get("is_claimed"),
                    "rating_value": rating.get("value"),
                    "votes_count": rating.get("votes_count"),
                    "api_cost_usd": task.get("cost"),
                }
            )
    return records


def parse_completed_business_listings_results(
    result_log: pd.DataFrame,
    raw_directory: Path,
    *,
    markets: set[str],
    expected_completed_requests: int,
) -> pd.DataFrame:
    """Parse a complete audited set of saved Business Listings responses."""

    required = {
        "task_tag",
        "market",
        "request_status",
        "raw_file",
        "retrieved_at_utc",
        "item_count",
    }
    missing = required - set(result_log.columns)
    if missing:
        raise KeyError(f"Business Listings result log is missing: {sorted(missing)}")
    clean_markets = {str(value).strip() for value in markets if str(value).strip()}
    if not clean_markets:
        raise ValueError("At least one market is required")
    completed = result_log.loc[
        result_log["request_status"].eq("completed")
        & result_log["market"].astype(str).isin(clean_markets)
    ].copy()
    if completed["task_tag"].astype(str).duplicated().any():
        raise ValueError("Completed Business Listings task tags must be unique")
    if len(completed) != int(expected_completed_requests):
        raise ValueError(
            "Completed Business Listings request count differs from the audited "
            f"page count: completed={len(completed)}, "
            f"audited={int(expected_completed_requests)}"
        )
    observed_markets = set(completed["market"].astype(str))
    if observed_markets != clean_markets:
        raise ValueError(
            "Completed Business Listings markets differ from the requested markets"
        )

    records: list[dict[str, Any]] = []
    expected_items = 0
    for row in completed.sort_values("task_tag").to_dict(orient="records"):
        raw_path = raw_directory / str(row["raw_file"])
        if not raw_path.is_file():
            raise FileNotFoundError(f"Missing raw Business Listings response: {raw_path}")
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        parsed = parse_business_listings_payload(
            payload,
            expected_tag=str(row["task_tag"]),
            market=str(row["market"]),
            retrieved_at_utc=str(row["retrieved_at_utc"]),
        )
        records.extend(parsed)
        expected_items += int(row["item_count"])
    if len(records) != expected_items:
        raise ValueError(
            "Parsed item count differs from the result log: "
            f"parsed={len(records)}, expected={expected_items}"
        )
    if not records:
        raise ValueError("Completed Business Listings responses contain no items")
    return pd.DataFrame.from_records(records)


def write_json_atomic(payload: Mapping[str, Any], path: Path) -> None:
    """Write one paid raw response without exposing a partial file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def deduplicate_business_listings(
    observations: pd.DataFrame,
) -> pd.DataFrame:
    """Collapse repeated category-group observations by CID or place ID."""

    required = {"cid", "place_id", "task_tag", "requested_location", "category"}
    missing = required - set(observations.columns)
    if missing:
        raise KeyError(f"Business Listings observations are missing: {sorted(missing)}")
    if observations.empty:
        return observations.copy()

    work = observations.reset_index(drop=True).copy()
    parents = list(range(len(work)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    seen: dict[tuple[str, str], int] = {}
    for index, row in work.iterrows():
        tokens: list[tuple[str, str]] = []
        for column in ("cid", "place_id"):
            value = row[column]
            if pd.notna(value) and str(value).strip():
                tokens.append((column, str(value).strip()))
        if not tokens:
            raise ValueError("Observation lacks both cid and place_id")
        for token in tokens:
            if token in seen:
                union(index, seen[token])
            else:
                seen[token] = index

    work["_component"] = [find(index) for index in range(len(work))]
    records: list[dict[str, Any]] = []
    for _, group in work.groupby("_component", sort=False):
        markets = sorted(set(group["requested_location"].astype(str)))
        if len(markets) != 1:
            raise ValueError("One stable business identity appears in multiple markets")
        completeness = group.notna().sum(axis=1)
        canonical_index = completeness.sort_values(
            ascending=False, kind="stable"
        ).index[0]
        canonical = work.loc[canonical_index].drop(labels="_component").to_dict()
        cid_values = sorted(
            {str(value).strip() for value in group["cid"].dropna() if str(value).strip()}
        )
        place_values = sorted(
            {
                str(value).strip()
                for value in group["place_id"].dropna()
                if str(value).strip()
            }
        )
        if len(cid_values) > 1 or len(place_values) > 1:
            raise ValueError("Linked Business Listings identities contain conflicting IDs")
        canonical["cid"] = cid_values[0] if cid_values else None
        canonical["place_id"] = place_values[0] if place_values else None
        canonical["profile_key"] = (
            f"google:cid:{cid_values[0]}"
            if cid_values
            else f"google:place_id:{place_values[0]}"
        )
        canonical["observation_count"] = len(group)
        canonical["observed_task_tags"] = "|".join(
            sorted(set(group["task_tag"].astype(str)))
        )
        canonical["observed_categories"] = "|".join(
            sorted(
                {
                    str(value).strip()
                    for value in group["category"].dropna()
                    if str(value).strip()
                }
            )
        )
        records.append(canonical)
    return pd.DataFrame.from_records(records).sort_values(
        ["requested_location", "profile_key"], ignore_index=True
    )
