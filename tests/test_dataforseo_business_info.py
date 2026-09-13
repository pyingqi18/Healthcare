"""Tests for batched Google Business Info task submission."""

from typing import Any

import pytest

from medical_ratings.dataforseo import DataForSEOClient


def task(cid: str) -> dict[str, object]:
    return {
        "task_tag": f"business_info:cid:{cid}",
        "clinic_key": f"google:cid:{cid}",
        "cid": cid,
        "query": f"cid:{cid}",
        "location_code": 2840,
        "language_code": "en",
        "priority": 1,
    }


def test_submit_business_info_batch_preserves_per_task_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DataForSEOClient("login", "password")
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        captured.update({"method": method, "url": url, **kwargs})
        return {
            "status_code": 20000,
            "tasks": [
                {
                    "id": "task-100",
                    "status_code": 20100,
                    "status_message": "Task Created.",
                    "cost": 0.0015,
                    "data": {"tag": "business_info:cid:100"},
                },
                {
                    "id": None,
                    "status_code": 40000,
                    "status_message": "Failed.",
                    "cost": 0,
                    "data": {"tag": "business_info:cid:200"},
                },
            ],
        }

    monkeypatch.setattr(client, "_request", fake_request)
    records = client.submit_business_info_batch(
        url="https://api.dataforseo.com/example/task_post",
        tasks=[task("100"), task("200")],
    )

    assert captured["method"] == "POST"
    assert captured["validate_tasks"] is False
    assert captured["json"][0] == {
        "keyword": "cid:100",
        "location_code": 2840,
        "language_code": "en",
        "priority": 1,
        "tag": "business_info:cid:100",
    }
    assert records[0]["submission_status"] == "submitted"
    assert records[0]["task_id"] == "task-100"
    assert records[1]["submission_status"] == "failed"
    assert len(str(records[0]["params_hash"])) == 64


def test_submit_business_info_batch_rejects_more_than_100_tasks() -> None:
    client = DataForSEOClient("login", "password")
    with pytest.raises(ValueError, match="1 to 100"):
        client.submit_business_info_batch(
            url="https://api.dataforseo.com/example/task_post",
            tasks=[task(str(cid)) for cid in range(101)],
        )


def test_submit_business_info_batch_rejects_query_cid_mismatch() -> None:
    client = DataForSEOClient("login", "password")
    row = task("100")
    row["query"] = "cid:999"
    with pytest.raises(ValueError, match="exactly match"):
        client.submit_business_info_batch(
            url="https://api.dataforseo.com/example/task_post",
            tasks=[row],
        )
