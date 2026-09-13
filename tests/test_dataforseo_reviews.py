"""Unit tests for DataForSEO Google Reviews task submission."""

from typing import Any

import pytest

from medical_ratings.dataforseo import DataForSEOClient


def test_submit_review_task_uses_place_id_and_preserves_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DataForSEOClient("login", "password")
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
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
                    "id": "review-task-123",
                    "status_code": 20100,
                }
            ],
        }

    monkeypatch.setattr(client, "_request", fake_request)

    record = client.submit_review_task(
        url="https://api.dataforseo.com/v3/business_data/google/reviews/task_post",
        requested_location="Syracuse_NY_M",
        location_code=1023416,
        place_id="place-123",
        language_code="en",
        depth=120,
        sort_by="newest",
        tag="clinic-key-123",
    )

    assert captured == {
        "method": "POST",
        "url": "https://api.dataforseo.com/v3/business_data/google/reviews/task_post",
        "json": [
            {
                "place_id": "place-123",
                "location_code": 1023416,
                "language_code": "en",
                "depth": 120,
                "sort_by": "newest",
                "tag": "clinic-key-123",
            }
        ],
    }
    assert record.task_id == "review-task-123"
    assert record.identifier_type == "place_id"
    assert record.identifier_value == "place-123"
    assert record.requested_location == "Syracuse_NY_M"
    assert record.location_code == 1023416
    assert record.depth == 120
    assert record.sort_by == "newest"
    assert record.tag == "clinic-key-123"
    assert len(record.params_hash) == 64


def test_submit_review_task_accepts_cid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DataForSEOClient("login", "password")

    monkeypatch.setattr(
        client,
        "_request",
        lambda *args, **kwargs: {
            "status_code": 20000,
            "tasks": [{"id": "review-task-456", "status_code": 20100}],
        },
    )

    record = client.submit_review_task(
        url="https://api.dataforseo.com/v3/business_data/google/reviews/task_post",
        requested_location="Malone_NY_S",
        location_code=1023114,
        cid="cid-456",
        depth=20,
    )

    assert record.identifier_type == "cid"
    assert record.identifier_value == "cid-456"


def test_submit_review_task_requires_exactly_one_business_identifier() -> None:
    client = DataForSEOClient("login", "password")
    url = "https://api.dataforseo.com/v3/business_data/google/reviews/task_post"

    with pytest.raises(ValueError, match="exactly one"):
        client.submit_review_task(
            url=url,
            requested_location="Syracuse_NY_M",
            location_code=1023416,
        )

    with pytest.raises(ValueError, match="exactly one"):
        client.submit_review_task(
            url=url,
            requested_location="Syracuse_NY_M",
            location_code=1023416,
            place_id="place-123",
            cid="cid-123",
        )


def review_batch_task(cid: str) -> dict[str, object]:
    return {
        "task_tag": f"reviews:cid:{cid}",
        "final_physical_location_id": f"location:{cid}",
        "clinic_key": f"google:cid:{cid}",
        "cid": cid,
        "identifier_type": "place_id",
        "identifier_value": f"place-{cid}",
        "requested_location": "Syracuse_NY_M",
        "location_code": 1023416,
        "language_code": "en",
        "sort_by": "newest",
        "planned_depth": 120,
    }


def test_submit_review_batch_preserves_status_and_parameters(
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
                    "id": "review-task-100",
                    "status_code": 20100,
                    "status_message": "Task Created.",
                    "cost": 0.009,
                    "data": {"tag": "reviews:cid:100"},
                },
                {
                    "id": None,
                    "status_code": 40000,
                    "status_message": "Failed.",
                    "cost": 0,
                    "data": {"tag": "reviews:cid:200"},
                },
            ],
        }

    monkeypatch.setattr(client, "_request", fake_request)
    records = client.submit_review_batch(
        url="https://api.dataforseo.com/example/reviews/task_post",
        tasks=[review_batch_task("100"), review_batch_task("200")],
    )

    assert captured["method"] == "POST"
    assert captured["validate_tasks"] is False
    assert captured["json"][0] == {
        "place_id": "place-100",
        "location_code": 1023416,
        "language_code": "en",
        "depth": 120,
        "sort_by": "newest",
        "tag": "reviews:cid:100",
    }
    assert records[0]["submission_status"] == "submitted"
    assert records[0]["task_id"] == "review-task-100"
    assert records[1]["submission_status"] == "failed"
    assert len(str(records[0]["params_hash"])) == 64


def test_submit_review_batch_rejects_more_than_100_tasks() -> None:
    client = DataForSEOClient("login", "password")
    try:
        client.submit_review_batch(
            url="https://api.dataforseo.com/example/reviews/task_post",
            tasks=[review_batch_task(str(cid)) for cid in range(101)],
        )
    except ValueError as error:
        assert "1 to 100" in str(error)
    else:
        raise AssertionError("Expected oversized review batch to fail")
