"""Unit tests for DataForSEO clinic search submission."""

from typing import Any

import pytest

from medical_ratings.dataforseo import DataForSEOClient


def test_authentication_uses_shared_request_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DataForSEOClient(" login ", " password ")
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        captured.update({"method": method, "url": url, **kwargs})
        return {"status_code": 20000}

    monkeypatch.setattr(client, "_request", fake_request)

    assert client.check_authentication() == {
        "api_status": 20000,
        "authenticated": True,
    }
    assert captured["method"] == "GET"
    assert captured["validate_tasks"] is False


def test_business_listings_filter_catalog_uses_non_task_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DataForSEOClient("login", "password")
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        captured.update({"method": method, "url": url, **kwargs})
        return {"status_code": 20000, "tasks": [{"result": [{"filters": {}}]}]}

    monkeypatch.setattr(client, "_request", fake_request)
    payload = client.get_business_listings_available_filters(
        "https://api.dataforseo.com/v3/business_data/business_listings/available_filters"
    )
    assert payload["status_code"] == 20000
    assert captured == {
        "method": "GET",
        "url": "https://api.dataforseo.com/v3/business_data/business_listings/available_filters",
        "validate_tasks": False,
    }


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


def test_submit_search_batch_uses_one_request_and_preserves_task_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DataForSEOClient("login", "password")
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        captured.update({"method": method, "url": url, **kwargs})
        return {
            "status_code": 20000,
            "tasks": [
                {"id": "id-1", "status_code": 20100, "data": {"tag": "tag-1"}, "cost": 0.0006},
                {"id": "id-2", "status_code": 20100, "data": {"tag": "tag-2"}, "cost": 0.0006},
            ],
        }

    monkeypatch.setattr(client, "_request", fake_request)
    records = client.submit_search_batch(
        url="https://api.dataforseo.com/example/task_post",
        tasks=[
            {"task_tag": "tag-1", "query": "dentist", "location_code": 1, "language_code": "en", "depth": 100, "priority": 1},
            {"task_tag": "tag-2", "query": "dental clinic", "location_code": 2, "language_code": "en", "depth": 100, "priority": 1},
        ],
    )
    assert captured["method"] == "POST"
    assert len(captured["json"]) == 2
    assert [row["task_id"] for row in records] == ["id-1", "id-2"]
    assert all(row["submission_status"] == "submitted" for row in records)


def test_tasks_ready_returns_only_explicit_completed_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DataForSEOClient("login", "password")
    monkeypatch.setattr(
        client,
        "_request",
        lambda *args, **kwargs: {
            "tasks": [{"result": [{"id": "ready-1"}, {"id": "ready-2"}]}]
        },
    )
    assert client.get_ready_task_ids("https://example/tasks_ready") == {
        "ready-1", "ready-2"
    }
