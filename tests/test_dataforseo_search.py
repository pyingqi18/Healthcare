"""Unit tests for DataForSEO clinic search submission."""

from typing import Any

import pytest

from medical_ratings.dataforseo import DataForSEOClient


def test_submit_search_task_preserves_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DataForSEOClient("login", "password")
    captured: dict[str, Any] = {}

    def fake_request(
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        captured.update(
            {
                "method": method,
                "url": url,
                "json": kwargs["json"],
            }
        )
        return {
            "status_code": 20000,
            "tasks": [
                {
                    "id": "search-task-123",
                    "status_code": 20100,
                }
            ],
        }

    monkeypatch.setattr(client, "_request", fake_request)

    record = client.submit_task(
        url="https://api.dataforseo.com/example/task_post",
        api_type="maps",
        query="dentist",
        location_code=1023416,
        language_code="en",
        depth=100,
        tag="Syracuse_NY_M:maps:general:03",
    )

    assert captured["json"] == [
        {
            "location_code": 1023416,
            "language_code": "en",
            "keyword": "dentist",
            "depth": 100,
            "tag": "Syracuse_NY_M:maps:general:03",
        }
    ]
    assert record.task_id == "search-task-123"
    assert record.tag == "Syracuse_NY_M:maps:general:03"