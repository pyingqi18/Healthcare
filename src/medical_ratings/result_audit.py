"""Aggregate audits for downloaded DataForSEO clinic-search results."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


AUDIT_FIELDS = (
    "cid",
    "place_id",
    "title",
    "address",
    "address_info.zip",
    "latitude",
    "longitude",
    "phone",
    "url",
    "category",
    "rating.value",
    "rating.votes_count",
)


def _items(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for task in payload.get("tasks") or []:
        if not isinstance(task, Mapping):
            continue
        for result in task.get("result") or []:
            if not isinstance(result, Mapping):
                continue
            for item in result.get("items") or []:
                if isinstance(item, Mapping):
                    yield item


def _nested_value(item: Mapping[str, Any], path: str) -> Any:
    value: Any = item
    for part in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _stable_id(item: Mapping[str, Any]) -> str | None:
    for field in ("cid", "place_id"):
        value = item.get(field)
        if _present(value):
            return f"{field}:{value}"
    return None


def audit_location_results(
    results: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize result structure without exposing clinic-level content."""

    task_counts: Counter[str] = Counter()
    region_task_counts: Counter[str] = Counter()
    item_counts: Counter[str] = Counter()
    region_item_counts: Counter[str] = Counter()
    item_types: dict[str, Counter[str]] = defaultdict(Counter)
    field_counts: dict[str, Counter[str]] = defaultdict(Counter)
    stable_ids: set[str] = set()
    cid_values: set[str] = set()
    place_id_values: set[str] = set()
    items_without_stable_id = 0
    total_items = 0

    for entry in results:
        api_type = str(entry["api_type"])
        region_key = str(entry["region_key"])
        payload = entry["payload"]
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")

        task_counts[api_type] += 1
        region_task_counts[region_key] += 1

        for item in _items(payload):
            total_items += 1
            item_counts[api_type] += 1
            region_item_counts[region_key] += 1
            item_types[api_type][str(item.get("type") or "missing")] += 1

            for field in AUDIT_FIELDS:
                if _present(_nested_value(item, field)):
                    field_counts[api_type][field] += 1

            cid = item.get("cid")
            place_id = item.get("place_id")
            if _present(cid):
                cid_values.add(str(cid))
            if _present(place_id):
                place_id_values.add(str(place_id))

            identifier = _stable_id(item)
            if identifier is None:
                items_without_stable_id += 1
            else:
                stable_ids.add(identifier)

    field_coverage: dict[str, dict[str, dict[str, int | float]]] = {}
    for api_type in sorted(task_counts):
        denominator = item_counts[api_type]
        field_coverage[api_type] = {}
        for field in AUDIT_FIELDS:
            present = field_counts[api_type][field]
            percent = round(100 * present / denominator, 1) if denominator else 0.0
            field_coverage[api_type][field] = {
                "present": present,
                "total": denominator,
                "percent": percent,
            }

    return {
        "result_tasks": sum(task_counts.values()),
        "tasks_by_api": dict(sorted(task_counts.items())),
        "tasks_by_region": dict(sorted(region_task_counts.items())),
        "result_items": total_items,
        "items_by_api": dict(sorted(item_counts.items())),
        "items_by_region": dict(sorted(region_item_counts.items())),
        "item_types_by_api": {
            api_type: dict(sorted(counts.items()))
            for api_type, counts in sorted(item_types.items())
        },
        "field_coverage_by_api": field_coverage,
        "identifiers": {
            "unique_cid": len(cid_values),
            "unique_place_id": len(place_id_values),
            "unique_stable_ids": len(stable_ids),
            "items_without_cid_or_place_id": items_without_stable_id,
            "repeated_observations": total_items - len(stable_ids),
        },
    }
