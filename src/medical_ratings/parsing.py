"""Parsers that retain API provenance and stable place identifiers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _iter_items(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    tasks = payload.get("tasks") or []
    for task in tasks:
        for result in task.get("result") or []:
            for item in result.get("items") or []:
                yield item


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
    for rank, item in enumerate(_iter_items(payload), start=1):
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
                "source_api": "maps",
                "query": query,
                "requested_location": requested_location,
                "retrieved_at_utc": retrieved_at_utc,
                "source_rank": rank,
                "place_id": item.get("place_id"),
                "cid": item.get("cid"),
                "title": item.get("title"),
                "address": item.get("address"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "zip": address_info.get("zip"),
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
    for rank, item in enumerate(_iter_items(payload), start=1):
        rating = item.get("rating") if isinstance(item.get("rating"), Mapping) else {}
        records.append(
            {
                "task_id": task_id,
                "source_api": "local_finder",
                "query": query,
                "requested_location": requested_location,
                "retrieved_at_utc": retrieved_at_utc,
                "source_rank": rank,
                "place_id": item.get("place_id"),
                "cid": item.get("cid"),
                "title": item.get("title"),
                "description": item.get("description"),
                "rating_value": rating.get("value"),
                "votes_count": rating.get("votes_count"),
                "item_type": item.get("type"),
            }
        )
    return records
