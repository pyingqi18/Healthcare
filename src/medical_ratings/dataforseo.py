"""DataForSEO task submission and retrieval with provenance retention."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from collections.abc import Mapping, Sequence
from typing import Any

import requests


USER_DATA_URL = "https://api.dataforseo.com/v3/appendix/user_data"


class DataForSEOError(RuntimeError):
    """Raised when an HTTP or task-level DataForSEO operation fails."""


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    api_type: str
    endpoint: str
    query: str
    location_code: int
    language_code: str
    depth: int
    params_hash: str
    submitted_at_utc: str
    tag: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the record to a serializable dictionary."""

        return asdict(self)


@dataclass(frozen=True)
class ReviewTaskRecord:
    """Provenance retained for one submitted Google Reviews task."""

    task_id: str
    api_type: str
    endpoint: str
    requested_location: str
    identifier_type: str
    identifier_value: str
    location_code: int
    language_code: str
    depth: int
    sort_by: str
    tag: str | None
    params_hash: str
    submitted_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        """Convert the record to a serializable dictionary."""

        return asdict(self)


class DataForSEOClient:
    """Small synchronous client for task-based DataForSEO endpoints."""

    def __init__(self, login: str, password: str, *, timeout: float = 60.0) -> None:
        clean_login = login.strip()
        clean_password = password.strip()
        if not clean_login or not clean_password:
            raise ValueError("DataForSEO login and password cannot be blank")
        self.auth = (clean_login, clean_password)
        self.timeout = timeout
        self.session = requests.Session()

    @staticmethod
    def _validate_response(
        payload: dict[str, Any],
        *,
        validate_tasks: bool = True,
    ) -> None:
        status_code = payload.get("status_code")
        if status_code is not None and int(status_code) >= 40000:
            raise DataForSEOError(
                f"DataForSEO request failed: {status_code} {payload.get('status_message')}"
            )

        if not validate_tasks:
            return

        tasks = payload.get("tasks") or []
        for task in tasks:
            task_code = task.get("status_code")
            if task_code is not None and int(task_code) >= 40000:
                raise DataForSEOError(
                    f"DataForSEO task failed: {task_code} {task.get('status_message')}"
                )

    def _request(
        self,
        method: str,
        url: str,
        *,
        validate_tasks: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = self.session.request(
            method,
            url,
            auth=self.auth,
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        payload = response.json()
        self._validate_response(payload, validate_tasks=validate_tasks)
        return payload

    def check_authentication(self) -> dict[str, Any]:
        """Call the free user-data endpoint and return a credential-safe summary."""

        payload = self._request(
            "GET",
            USER_DATA_URL,
            validate_tasks=False,
        )
        api_status = payload.get("status_code")
        return {
            "api_status": api_status,
            "authenticated": api_status == 20000,
        }

    def get_business_listings_available_filters(
        self,
        url: str,
    ) -> dict[str, Any]:
        """Read the non-task Business Listings filter catalog."""

        clean_url = str(url).strip()
        if not clean_url.startswith("https://api.dataforseo.com/"):
            raise ValueError("Business Listings filter URL must use the DataForSEO API")
        return self._request("GET", clean_url, validate_tasks=False)

    def search_business_listings_live(
        self,
        *,
        url: str,
        categories: Sequence[str],
        location_coordinate: str,
        limit: int,
        tag: str,
        offset: int = 0,
        offset_token: str | None = None,
        filters: Sequence[Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Run one live Business Listings request and retain its provenance."""

        clean_categories = [str(value).strip() for value in categories]
        if not 1 <= len(clean_categories) <= 10:
            raise ValueError("Business Listings requires 1 to 10 categories")
        if any(not value for value in clean_categories):
            raise ValueError("Business Listings categories cannot be blank")
        if len(clean_categories) != len(set(clean_categories)):
            raise ValueError("Business Listings categories cannot contain duplicates")
        clean_tag = str(tag).strip()
        if not clean_tag or len(clean_tag) > 255:
            raise ValueError("tag must contain 1 to 255 characters")
        clean_coordinate = str(location_coordinate).strip()
        coordinate_parts = clean_coordinate.split(",")
        if len(coordinate_parts) != 3:
            raise ValueError(
                "location_coordinate must use latitude,longitude,radius"
            )
        try:
            latitude, longitude, radius = map(float, coordinate_parts)
        except ValueError as error:
            raise ValueError("location_coordinate contains nonnumeric values") from error
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("location_coordinate latitude or longitude is invalid")
        if not 1 <= radius <= 100000:
            raise ValueError("Business Listings radius must be 1 to 100000 km")
        parsed_limit = int(limit)
        if not 1 <= parsed_limit <= 1000:
            raise ValueError("Business Listings limit must be 1 to 1000")
        parsed_offset = int(offset)
        if parsed_offset < 0:
            raise ValueError("Business Listings offset cannot be negative")
        clean_offset_token = None
        if offset_token is not None:
            clean_offset_token = str(offset_token).strip()
            if not clean_offset_token:
                raise ValueError("Business Listings offset_token cannot be blank")
            if parsed_offset != 0:
                raise ValueError("Use offset or offset_token, not both")

        request_row = {
            "categories": clean_categories,
            "location_coordinate": clean_coordinate,
            "limit": parsed_limit,
            "tag": clean_tag,
        }
        clean_filters = None
        if filters is not None:
            clean_filters = list(filters)
            if not clean_filters or len(clean_filters) > 15:
                raise ValueError("Business Listings filters are empty or too long")
            condition_count = sum(
                isinstance(value, Sequence) and not isinstance(value, str)
                for value in clean_filters
            )
            if condition_count < 1 or condition_count > 8:
                raise ValueError("Business Listings requires 1 to 8 filter conditions")
            request_row["filters"] = clean_filters
        if clean_offset_token is not None:
            request_row["offset_token"] = clean_offset_token
        elif parsed_offset:
            request_row["offset"] = parsed_offset
        payload = self._request("POST", url, json=[request_row])
        if int(payload.get("status_code", -1)) != 20000:
            raise DataForSEOError(
                "Business Listings live response was not completed with status 20000"
            )
        if int(payload.get("tasks_count", -1)) != 1:
            raise DataForSEOError(
                "Business Listings live response must report tasks_count=1"
            )
        if int(payload.get("tasks_error", -1)) != 0:
            raise DataForSEOError(
                "Business Listings live response must report tasks_error=0"
            )
        tasks = payload.get("tasks") or []
        if len(tasks) != 1:
            raise DataForSEOError(
                "Business Listings live response must contain exactly one task"
            )
        task = tasks[0]
        if int(task.get("status_code", -1)) != 20000:
            raise DataForSEOError(
                "Business Listings live task was not completed with status 20000"
            )
        response_data = task.get("data") or {}
        if str(response_data.get("tag", "")) != clean_tag:
            raise DataForSEOError("Business Listings response tag does not match request")

        results = task.get("result") or []
        if len(results) != 1 or not isinstance(results[0], Mapping):
            raise DataForSEOError(
                "Completed Business Listings live task must contain one result object"
            )
        result = results[0]
        items = result.get("items") or []
        if not isinstance(items, list):
            raise DataForSEOError("Business Listings result items must be a list")
        item_count = len(items)
        if result.get("count") is None or int(result["count"]) != item_count:
            raise DataForSEOError(
                "Business Listings result count does not match the items array"
            )
        if result.get("total_count") is None:
            raise DataForSEOError("Business Listings result is missing total_count")
        total_count = int(result["total_count"])
        if total_count < 0 or total_count < item_count:
            raise DataForSEOError("Business Listings total_count is inconsistent")
        if clean_offset_token is None and total_count < parsed_offset + item_count:
            raise DataForSEOError(
                "Business Listings total_count is smaller than the saved offset coverage"
            )
        next_offset_token = None
        token = result.get("offset_token")
        if isinstance(token, Mapping):
            token = token.get("value") or token.get("token")
        if token is not None and str(token).strip():
            next_offset_token = str(token).strip()
        page_has_more = (
            next_offset_token is not None
            if clean_offset_token is not None
            else (
                total_count is not None
                and total_count > parsed_offset + item_count
            )
        )
        canonical = json.dumps(request_row, sort_keys=True, separators=(",", ":"))
        provenance = {
            "task_tag": clean_tag,
            "task_id": None if task.get("id") is None else str(task.get("id")),
            "api_type": "business_listings_live",
            "endpoint": url,
            "location_coordinate": clean_coordinate,
            "categories": "|".join(clean_categories),
            "filters": (
                None
                if clean_filters is None
                else json.dumps(clean_filters, separators=(",", ":"))
            ),
            "category_count": len(clean_categories),
            "limit": parsed_limit,
            "offset": parsed_offset,
            "offset_token_used": clean_offset_token,
            "params_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "api_status_code": task.get("status_code"),
            "api_status_message": task.get("status_message"),
            "api_cost_usd": task.get("cost"),
            "item_count": item_count,
            "total_count": total_count,
            "next_offset_token": next_offset_token,
            "page_has_more": page_has_more,
            "request_status": "completed",
        }
        return payload, provenance

    def submit_business_info_batch(
        self,
        *,
        url: str,
        tasks: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Submit up to 100 Business Info tasks and retain per-task status."""

        if not 1 <= len(tasks) <= 100:
            raise ValueError("Business Info batch must contain 1 to 100 tasks")

        payload_rows: list[dict[str, Any]] = []
        source_rows: list[dict[str, Any]] = []
        observed_tags: set[str] = set()
        for source in tasks:
            required = {
                "task_tag",
                "clinic_key",
                "cid",
                "query",
                "location_code",
                "language_code",
                "priority",
            }
            missing = required - set(source)
            if missing:
                raise KeyError(
                    f"Business Info task is missing fields: {sorted(missing)}"
                )

            tag = str(source["task_tag"]).strip()
            cid = str(source["cid"]).strip()
            query = str(source["query"]).strip()
            if not tag or len(tag) > 255:
                raise ValueError("task_tag must contain 1 to 255 characters")
            if tag in observed_tags:
                raise ValueError("Business Info batch contains duplicate task_tag values")
            if not cid.isdigit() or query != f"cid:{cid}":
                raise ValueError("Business Info query must exactly match cid:<cid>")
            observed_tags.add(tag)

            payload_row = {
                "keyword": query,
                "location_code": int(source["location_code"]),
                "language_code": str(source["language_code"]),
                "priority": int(source["priority"]),
                "tag": tag,
            }
            if payload_row["priority"] not in {1, 2}:
                raise ValueError("priority must be 1 or 2")
            payload_rows.append(payload_row)
            source_rows.append(dict(source))

        payload = self._request(
            "POST",
            url,
            json=payload_rows,
            validate_tasks=False,
        )
        response_tasks = payload.get("tasks") or []
        if len(response_tasks) != len(payload_rows):
            raise DataForSEOError(
                "Business Info response task count does not match request count"
            )

        submitted_at = datetime.now(timezone.utc).isoformat()
        records: list[dict[str, Any]] = []
        for source, request_row, response_task in zip(
            source_rows,
            payload_rows,
            response_tasks,
            strict=True,
        ):
            response_data = response_task.get("data") or {}
            response_tag = response_data.get("tag")
            if response_tag is not None and str(response_tag) != request_row["tag"]:
                raise DataForSEOError(
                    "Business Info response tag does not match request order"
                )

            canonical = json.dumps(
                request_row,
                sort_keys=True,
                separators=(",", ":"),
            )
            status_code = response_task.get("status_code")
            task_id = response_task.get("id")
            submitted = (
                status_code is not None
                and int(status_code) < 40000
                and bool(task_id)
            )
            records.append(
                {
                    **source,
                    "task_id": None if task_id is None else str(task_id),
                    "api_type": "google_my_business_info",
                    "endpoint": url,
                    "params_hash": hashlib.sha256(
                        canonical.encode("utf-8")
                    ).hexdigest(),
                    "submitted_at_utc": submitted_at,
                    "api_status_code": status_code,
                    "api_status_message": response_task.get("status_message"),
                    "api_cost_usd": response_task.get("cost"),
                    "submission_status": "submitted" if submitted else "failed",
                }
            )
        return records

    def submit_review_batch(
        self,
        *,
        url: str,
        tasks: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Submit up to 100 Google Reviews tasks with per-task provenance."""

        if not 1 <= len(tasks) <= 100:
            raise ValueError("Google Reviews batch must contain 1 to 100 tasks")

        payload_rows: list[dict[str, Any]] = []
        source_rows: list[dict[str, Any]] = []
        observed_tags: set[str] = set()
        for source in tasks:
            required = {
                "task_tag",
                "final_physical_location_id",
                "clinic_key",
                "cid",
                "identifier_type",
                "identifier_value",
                "requested_location",
                "location_code",
                "language_code",
                "sort_by",
                "planned_depth",
            }
            missing = required - set(source)
            if missing:
                raise KeyError(
                    f"Google Reviews task is missing fields: {sorted(missing)}"
                )

            tag = str(source["task_tag"]).strip()
            identifier_type = str(source["identifier_type"]).strip()
            identifier_value = str(source["identifier_value"]).strip()
            if not tag or len(tag) > 255:
                raise ValueError("task_tag must contain 1 to 255 characters")
            if tag in observed_tags:
                raise ValueError("Google Reviews batch contains duplicate task tags")
            if identifier_type not in {"place_id", "cid"}:
                raise ValueError("Review identifier_type must be place_id or cid")
            if not identifier_value:
                raise ValueError("Review identifier_value cannot be blank")
            observed_tags.add(tag)

            depth = int(source["planned_depth"])
            if not 1 <= depth <= 4490:
                raise ValueError("Review depth must be between 1 and 4490")
            sort_by = str(source["sort_by"])
            if sort_by not in {
                "newest",
                "highest_rating",
                "lowest_rating",
                "relevant",
            }:
                raise ValueError("Invalid Google Reviews sort order")
            request_row = {
                identifier_type: identifier_value,
                "location_code": int(source["location_code"]),
                "language_code": str(source["language_code"]),
                "depth": depth,
                "sort_by": sort_by,
                "tag": tag,
            }
            payload_rows.append(request_row)
            source_rows.append(dict(source))

        payload = self._request(
            "POST",
            url,
            json=payload_rows,
            validate_tasks=False,
        )
        response_tasks = payload.get("tasks") or []
        if len(response_tasks) != len(payload_rows):
            raise DataForSEOError(
                "Google Reviews response task count does not match request count"
            )

        submitted_at = datetime.now(timezone.utc).isoformat()
        records: list[dict[str, Any]] = []
        for source, request_row, response_task in zip(
            source_rows,
            payload_rows,
            response_tasks,
            strict=True,
        ):
            response_data = response_task.get("data") or {}
            response_tag = response_data.get("tag")
            if response_tag is not None and str(response_tag) != request_row["tag"]:
                raise DataForSEOError(
                    "Google Reviews response tag does not match request order"
                )
            canonical = json.dumps(
                request_row,
                sort_keys=True,
                separators=(",", ":"),
            )
            status_code = response_task.get("status_code")
            task_id = response_task.get("id")
            submitted = (
                status_code is not None
                and int(status_code) < 40000
                and bool(task_id)
            )
            records.append(
                {
                    **source,
                    "task_id": None if task_id is None else str(task_id),
                    "api_type": "google_reviews",
                    "endpoint": url,
                    "params_hash": hashlib.sha256(
                        canonical.encode("utf-8")
                    ).hexdigest(),
                    "submitted_at_utc": submitted_at,
                    "api_status_code": status_code,
                    "api_status_message": response_task.get("status_message"),
                    "api_cost_usd": response_task.get("cost"),
                    "submission_status": "submitted" if submitted else "failed",
                }
            )
        return records

    def submit_task(
        self,
        *,
        url: str,
        api_type: str,
        query: str,
        location_code: int,
        language_code: str = "en",
        depth: int = 100,
        tag: str | None = None,
    ) -> TaskRecord:
        """Submit one task and return a provenance-complete task record."""

        if tag is not None and len(tag) > 255:
            raise ValueError(
                "tag must contain no more than 255 characters"
            )

        request_payload = {
            "location_code": int(location_code),
            "language_code": language_code,
            "keyword": query,
            "depth": int(depth),
        }

        if tag is not None:
            request_payload["tag"] = tag

        payload = self._request(
            "POST",
            url,
            json=[request_payload],
        )

        tasks = payload.get("tasks") or []

        if not tasks or not tasks[0].get("id"):
            raise DataForSEOError(
                "Task submission returned no task ID"
            )

        canonical = json.dumps(
            request_payload,
            sort_keys=True,
            separators=(",", ":"),
        )

        return TaskRecord(
            task_id=str(tasks[0]["id"]),
            api_type=api_type,
            endpoint=url,
            query=query,
            location_code=int(location_code),
            language_code=language_code,
            depth=int(depth),
            params_hash=hashlib.sha256(
                canonical.encode("utf-8")
            ).hexdigest(),
            submitted_at_utc=datetime.now(
                timezone.utc
            ).isoformat(),
            tag=tag,
        )

    def submit_search_batch(
        self,
        *,
        url: str,
        tasks: Sequence[Mapping[str, Any]],
        api_type: str = "maps",
    ) -> list[dict[str, Any]]:
        """Submit up to 100 Standard SERP tasks in one HTTP request."""

        if not 1 <= len(tasks) <= 100:
            raise ValueError("Search batch must contain 1 to 100 tasks")
        payload_rows: list[dict[str, Any]] = []
        source_rows: list[dict[str, Any]] = []
        tags: set[str] = set()
        for source in tasks:
            tag = str(source.get("task_tag", "")).strip()
            query = str(source.get("query", "")).strip()
            if not tag or not query:
                raise ValueError("Search tasks require nonblank task_tag and query")
            if tag in tags:
                raise ValueError("Search batch contains duplicate task tags")
            tags.add(tag)
            request_row = {
                "keyword": query,
                "location_code": int(source["location_code"]),
                "language_code": str(source.get("language_code", "en")),
                "depth": int(source.get("depth", 100)),
                "priority": int(source.get("priority", 1)),
                "tag": tag,
            }
            if not 1 <= request_row["depth"] <= 700:
                raise ValueError("Search depth must be between 1 and 700")
            payload_rows.append(request_row)
            source_rows.append(dict(source))
        payload = self._request(
            "POST", url, json=payload_rows, validate_tasks=False
        )
        response_tasks = payload.get("tasks") or []
        if len(response_tasks) != len(payload_rows):
            raise DataForSEOError(
                "Search response task count does not match submitted task count"
            )
        submitted_at = datetime.now(timezone.utc).isoformat()
        records: list[dict[str, Any]] = []
        for source, request_row, response_task in zip(
            source_rows, payload_rows, response_tasks, strict=True
        ):
            response_tag = (response_task.get("data") or {}).get("tag")
            if response_tag is not None and str(response_tag) != request_row["tag"]:
                raise DataForSEOError("Search response tag does not match request order")
            canonical = json.dumps(request_row, sort_keys=True, separators=(",", ":"))
            status_code = response_task.get("status_code")
            task_id = response_task.get("id")
            submitted = (
                status_code is not None
                and int(status_code) < 40000
                and bool(task_id)
            )
            records.append(
                {
                    **source,
                    "task_id": None if task_id is None else str(task_id),
                    "api_type": api_type,
                    "endpoint": url,
                    "params_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                    "submitted_at_utc": submitted_at,
                    "api_status_code": status_code,
                    "api_status_message": response_task.get("status_message"),
                    "api_cost_usd": response_task.get("cost"),
                    "submission_status": "submitted" if submitted else "failed",
                }
            )
        return records

    def get_ready_task_ids(self, url: str) -> set[str]:
        """Return task IDs explicitly reported complete by Tasks Ready."""

        payload = self._request("GET", url)
        tasks = payload.get("tasks") or []
        if len(tasks) != 1:
            raise DataForSEOError("Tasks Ready response must contain one task block")
        result = tasks[0].get("result") or []
        return {
            str(row["id"])
            for row in result
            if isinstance(row, Mapping) and row.get("id")
        }

    def submit_review_task(
        self,
        *,
        url: str,
        requested_location: str,
        location_code: int,
        place_id: str | None = None,
        cid: str | None = None,
        keyword: str | None = None,
        language_code: str = "en",
        depth: int = 10,
        sort_by: str = "newest",
        tag: str | None = None,
    ) -> ReviewTaskRecord:
        """Submit one Google Reviews task using one business identifier."""

        identifiers = {
            "place_id": place_id,
            "cid": cid,
            "keyword": keyword,
        }
        supplied_identifiers = {
            name: str(value).strip()
            for name, value in identifiers.items()
            if value is not None and str(value).strip()
        }

        if len(supplied_identifiers) != 1:
            raise ValueError(
                "Provide exactly one of place_id, cid, or keyword"
            )

        parsed_depth = int(depth)
        if not 1 <= parsed_depth <= 4490:
            raise ValueError("depth must be between 1 and 4490")

        valid_sort_values = {
            "newest",
            "highest_rating",
            "lowest_rating",
            "relevant",
        }
        if sort_by not in valid_sort_values:
            raise ValueError(
                f"sort_by must be one of {sorted(valid_sort_values)}"
            )

        if tag is not None and len(tag) > 255:
            raise ValueError("tag must contain no more than 255 characters")

        identifier_type, identifier_value = next(
            iter(supplied_identifiers.items())
        )
        request_payload: dict[str, Any] = {
            identifier_type: identifier_value,
            "location_code": int(location_code),
            "language_code": language_code,
            "depth": parsed_depth,
            "sort_by": sort_by,
        }
        if tag is not None:
            request_payload["tag"] = tag

        payload = self._request("POST", url, json=[request_payload])
        tasks = payload.get("tasks") or []
        if not tasks or not tasks[0].get("id"):
            raise DataForSEOError("Review task submission returned no task ID")

        canonical = json.dumps(
            request_payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        return ReviewTaskRecord(
            task_id=str(tasks[0]["id"]),
            api_type="google_reviews",
            endpoint=url,
            requested_location=requested_location,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            location_code=int(location_code),
            language_code=language_code,
            depth=parsed_depth,
            sort_by=sort_by,
            tag=tag,
            params_hash=hashlib.sha256(
                canonical.encode("utf-8")
            ).hexdigest(),
            submitted_at_utc=datetime.now(timezone.utc).isoformat(),
        )

    def get_task(self, url_template: str, task_id: str) -> dict[str, Any]:
        """Retrieve and validate one task result."""

        return self._request("GET", url_template.format(task_id=task_id))

    def poll_task(
        self,
        url_template: str,
        task_id: str,
        *,
        max_attempts: int,
        interval_seconds: float,
    ) -> dict[str, Any]:
        """Poll until a task contains a non-empty result or attempts are exhausted."""

        for attempt in range(1, max_attempts + 1):
            payload = self.get_task(url_template, task_id)
            tasks = payload.get("tasks") or []
            if tasks and tasks[0].get("result") is not None:
                return payload
            if attempt < max_attempts:
                time.sleep(interval_seconds)
        raise TimeoutError(f"Task {task_id} did not complete after {max_attempts} attempts")
