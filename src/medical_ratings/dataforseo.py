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
    ) -> TaskRecord:
        """Submit one task and return a provenance-complete task record."""

        request_payload = {
            "location_code": int(location_code),
            "language_code": language_code,
            "keyword": query,
            "depth": int(depth),
        }
        payload = self._request("POST", url, json=[request_payload])
        tasks = payload.get("tasks") or []
        if not tasks or not tasks[0].get("id"):
            raise DataForSEOError("Task submission returned no task ID")

        canonical = json.dumps(request_payload, sort_keys=True, separators=(",", ":"))
        return TaskRecord(
            task_id=str(tasks[0]["id"]),
            api_type=api_type,
            endpoint=url,
            query=query,
            location_code=int(location_code),
            language_code=language_code,
            depth=int(depth),
            params_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
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
