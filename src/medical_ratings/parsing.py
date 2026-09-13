"""Parsers that retain API provenance and stable place identifiers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
from typing import Any


def _iter_items(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    tasks = payload.get("tasks") or []
    for task in tasks:
        for result in task.get("result") or []:
            for item in result.get("items") or []:
                yield item


def _iter_search_items(
    payload: Mapping[str, Any],
) -> Iterable[
    tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]
]:
    """Yield task, result, and item context for SERP search payloads."""

    for task in payload.get("tasks") or []:
        if not isinstance(task, Mapping):
            continue
        for result in task.get("result") or []:
            if not isinstance(result, Mapping):
                continue
            for item in result.get("items") or []:
                if isinstance(item, Mapping):
                    yield task, result, item


def _task_tag(task: Mapping[str, Any]) -> Any:
    data = task.get("data")
    if not isinstance(data, Mapping):
        return None
    return data.get("tag")


def _json_text(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def parse_business_info_payload(
    payload: Mapping[str, Any],
    *,
    task_id: str,
    query: str,
    retrieved_at_utc: str,
) -> list[dict[str, Any]]:
    """Parse exact-CID Google Business Info items with full provenance."""

    records: list[dict[str, Any]] = []
    for task, result, item in _iter_search_items(payload):
        rating = item.get("rating") if isinstance(item.get("rating"), Mapping) else {}
        distribution = (
            item.get("rating_distribution")
            if isinstance(item.get("rating_distribution"), Mapping)
            else {}
        )
        address_info = (
            item.get("address_info")
            if isinstance(item.get("address_info"), Mapping)
            else {}
        )
        work_time = (
            item.get("work_time")
            if isinstance(item.get("work_time"), Mapping)
            else {}
        )
        records.append(
            {
                "task_id": task_id,
                "task_tag": _task_tag(task),
                "source_api": "google_my_business_info",
                "query": query,
                "result_keyword": result.get("keyword"),
                "retrieved_at_utc": retrieved_at_utc,
                "location_code": result.get("location_code"),
                "language_code": result.get("language_code"),
                "result_datetime_utc": result.get("datetime"),
                "item_type": item.get("type"),
                "cid": item.get("cid"),
                "place_id": item.get("place_id"),
                "feature_id": item.get("feature_id"),
                "title": item.get("title"),
                "original_title": item.get("original_title"),
                "description": item.get("description"),
                "category": item.get("category"),
                "category_ids_json": _json_text(item.get("category_ids")),
                "additional_categories_json": _json_text(
                    item.get("additional_categories")
                ),
                "address": item.get("address"),
                "address_street": address_info.get("address"),
                "address_borough": address_info.get("borough"),
                "city": address_info.get("city"),
                "zip": address_info.get("zip"),
                "address_region": address_info.get("region"),
                "country_code": address_info.get("country_code"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "phone": item.get("phone"),
                "domain": item.get("domain"),
                "url": item.get("url"),
                "contact_url": item.get("contact_url"),
                "book_online_url": item.get("book_online_url"),
                "rating_value": rating.get("value"),
                "votes_count": rating.get("votes_count"),
                **{
                    f"rating_{star}_star": distribution.get(str(star))
                    for star in range(1, 6)
                },
                "is_claimed": item.get("is_claimed"),
                "current_status": work_time.get("current_status"),
                "is_directory_item": item.get("is_directory_item"),
            }
        )
    return records


def parse_maps_payload(
    payload: Mapping[str, Any],
    *,
    task_id: str,
    query: str,
    requested_location: str,
    retrieved_at_utc: str,
) -> list[dict[str, Any]]:
    """Parse Maps items while preserving task and query provenance."""

    records: list[dict[str, Any]] = []
    for fallback_rank, (task, result, item) in enumerate(
        _iter_search_items(payload),
        start=1,
    ):
        rating = item.get("rating") if isinstance(item.get("rating"), Mapping) else {}
        distribution = (
            item.get("rating_distribution")
            if isinstance(item.get("rating_distribution"), Mapping)
            else {}
        )
        address_info = (
            item.get("address_info")
            if isinstance(item.get("address_info"), Mapping)
            else {}
        )
        records.append(
            {
                "task_id": task_id,
                "task_tag": _task_tag(task),
                "source_api": "maps",
                "query": query,
                "requested_location": requested_location,
                "retrieved_at_utc": retrieved_at_utc,
                "location_code": result.get("location_code"),
                "language_code": result.get("language_code"),
                "result_datetime_utc": result.get("datetime"),
                "source_rank": item.get("rank_absolute") or fallback_rank,
                "rank_group": item.get("rank_group"),
                "rank_absolute": item.get("rank_absolute"),
                "place_id": item.get("place_id"),
                "cid": item.get("cid"),
                "title": item.get("title"),
                "category": item.get("category"),
                "address": item.get("address"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "zip": address_info.get("zip"),
                "phone": item.get("phone"),
                "domain": item.get("domain"),
                "url": item.get("url"),
                "rating_value": rating.get("value"),
                "votes_count": rating.get("votes_count"),
                **{f"rating_{star}_star": distribution.get(str(star)) for star in range(1, 6)},
                "item_type": item.get("type"),
            }
        )
    return records


def parse_local_finder_payload(
    payload: Mapping[str, Any],
    *,
    task_id: str,
    query: str,
    requested_location: str,
    retrieved_at_utc: str,
) -> list[dict[str, Any]]:
    """Parse Local Finder items while preserving task and query provenance."""

    records: list[dict[str, Any]] = []
    for fallback_rank, (task, result, item) in enumerate(
        _iter_search_items(payload),
        start=1,
    ):
        rating = item.get("rating") if isinstance(item.get("rating"), Mapping) else {}
        records.append(
            {
                "task_id": task_id,
                "task_tag": _task_tag(task),
                "source_api": "local_finder",
                "query": query,
                "requested_location": requested_location,
                "retrieved_at_utc": retrieved_at_utc,
                "location_code": result.get("location_code"),
                "language_code": result.get("language_code"),
                "result_datetime_utc": result.get("datetime"),
                "source_rank": item.get("rank_absolute") or fallback_rank,
                "rank_group": item.get("rank_group"),
                "rank_absolute": item.get("rank_absolute"),
                "place_id": item.get("place_id"),
                "cid": item.get("cid"),
                "title": item.get("title"),
                "description": item.get("description"),
                "phone": item.get("phone"),
                "domain": item.get("domain"),
                "url": item.get("url"),
                "booking_url": item.get("booking_url"),
                "is_paid": item.get("is_paid"),
                "rating_value": rating.get("value"),
                "votes_count": rating.get("votes_count"),
                "item_type": item.get("type"),
            }
        )
    return records


def parse_reviews_payload(
    payload: Mapping[str, Any],
    *,
    task_id: str,
    requested_location: str,
    retrieved_at_utc: str,
) -> list[dict[str, Any]]:
    """Parse Google review results while preserving stable identifiers."""

    records: list[dict[str, Any]] = []

    for task in payload.get("tasks") or []:
        if not isinstance(task, Mapping):
            continue

        for result in task.get("result") or []:
            if not isinstance(result, Mapping):
                continue

            business_rating = (
                result.get("rating")
                if isinstance(result.get("rating"), Mapping)
                else {}
            )

            for item in result.get("items") or []:
                if not isinstance(item, Mapping):
                    continue

                review_rating = (
                    item.get("rating")
                    if isinstance(item.get("rating"), Mapping)
                    else {}
                )

                records.append(
                    {
                        "task_id": task_id,
                        "source_api": "google_reviews",
                        "requested_location": requested_location,
                        "retrieved_at_utc": retrieved_at_utc,
                        "location_code": result.get("location_code"),
                        "language_code": result.get("language_code"),
                        "result_datetime_utc": result.get("datetime"),
                        "place_id": result.get("place_id"),
                        "cid": result.get("cid"),
                        "business_title": result.get("title"),
                        "business_sub_title": result.get("sub_title"),
                        "business_rating_value": business_rating.get("value"),
                        "business_votes_count": business_rating.get("votes_count"),
                        "business_reviews_count": result.get("reviews_count"),
                        "review_id": item.get("review_id"),
                        "review_rank": item.get("rank_absolute"),
                        "review_timestamp_utc": item.get("timestamp"),
                        "rating_value": review_rating.get("value"),
                        "rating_max": review_rating.get("rating_max"),
                        "review_text": item.get("review_text"),
                        "original_review_text": item.get("original_review_text"),
                        "original_language": item.get("original_language"),
                        "profile_name": item.get("profile_name"),
                        "profile_url": item.get("profile_url"),
                        "review_url": item.get("review_url"),
                        "local_guide": item.get("local_guide"),
                        "reviewer_reviews_count": item.get("reviews_count"),
                        "reviewer_photos_count": item.get("photos_count"),
                        "owner_answer": item.get("owner_answer"),
                        "original_owner_answer": item.get(
                            "original_owner_answer"
                        ),
                        "owner_timestamp_utc": item.get("owner_timestamp"),
                    }
                )

    return records
