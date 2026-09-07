"""DataForSEO task submission and retrieval with provenance retention."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import requests


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
        self.auth = (login, password)
        self.timeout = timeout
        self.session = requests.Session()

    @staticmethod
    def _validate_response(payload: dict[str, Any]) -> None:
        status_code = payload.get("status_code")
        if status_code is not None and int(status_code) >= 40000:
            raise DataForSEOError(
                f"DataForSEO request failed: {status_code} {payload.get('status_message')}"
            )

        tasks = payload.get("tasks") or []
        for task in tasks:
            task_code = task.get("status_code")
            if task_code is not None and int(task_code) >= 40000:
                raise DataForSEOError(
                    f"DataForSEO task failed: {task_code} {task.get('status_message')}"
                )

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        response = self.session.request(
            method,
            url,
            auth=self.auth,
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        payload = response.json()
        self._validate_response(payload)
        return payload

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
