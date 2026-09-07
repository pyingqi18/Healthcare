"""Unit tests for DataForSEO response parsers."""

from medical_ratings.parsing import parse_reviews_payload


def test_parse_reviews_payload_preserves_stable_ids_and_provenance() -> None:
    payload = {
        "tasks": [
            {
                "id": "task-123",
                "result": [
                    {
                        "title": "Clinic A",
                        "sub_title": "1 Main St",
                        "location_code": 1023416,
                        "place_id": "place-123",
                        "cid": "cid-123",
                        "items": [
                            {
                                "rank_absolute": 1,
                                "review_id": "review-123",
                                "review_text": "Good visit",
                                "original_review_text": None,
                                "original_language": "en",
                                "timestamp": "2025-06-01 12:30:00 +00:00",
                                "rating": {
                                    "value": 5,
                                    "rating_max": 5,
                                },
                                "profile_name": "Reviewer A",
                                "profile_url": "https://example.com/profile",
                                "review_url": "https://example.com/review",
                                "owner_answer": "Thank you",
                                "owner_timestamp": "2025-06-02 08:00:00 +00:00",
                            }
                        ],
                    }
                ],
            }
        ]
    }

    records = parse_reviews_payload(
        payload,
        task_id="task-123",
        requested_location="Syracuse_NY_M",
        retrieved_at_utc="2026-09-07T12:00:00+00:00",
    )

    assert len(records) == 1
    record = records[0]

    assert record["task_id"] == "task-123"
    assert record["source_api"] == "google_reviews"
    assert record["requested_location"] == "Syracuse_NY_M"
    assert record["retrieved_at_utc"] == "2026-09-07T12:00:00+00:00"
    assert record["location_code"] == 1023416
    assert record["place_id"] == "place-123"
    assert record["cid"] == "cid-123"
    assert record["review_id"] == "review-123"
    assert record["review_timestamp_utc"] == "2025-06-01 12:30:00 +00:00"
    assert record["rating_value"] == 5
    assert record["review_text"] == "Good visit"
    assert record["owner_answer"] == "Thank you"


def test_parse_reviews_payload_accepts_empty_results() -> None:
    payload = {"tasks": [{"id": "task-empty", "result": []}]}

    records = parse_reviews_payload(
        payload,
        task_id="task-empty",
        requested_location="Malone_NY_S",
        retrieved_at_utc="2026-09-07T12:00:00+00:00",
    )

    assert records == []
