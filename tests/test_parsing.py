"""Unit tests for DataForSEO response parsers."""

import json

from medical_ratings.parsing import (
    parse_local_finder_payload,
    parse_maps_payload,
    parse_reviews_payload,
)


def test_parse_maps_payload_preserves_business_fields_and_provenance() -> None:
    payload = {
        "tasks": [
            {
                "id": "maps-task-123",
                "data": {"tag": "Syracuse_NY_M:maps:general:01"},
                "result": [
                    {
                        "location_code": 1023416,
                        "language_code": "en",
                        "datetime": "2026-09-07 20:00:00 +00:00",
                        "items": [
                            {
                                "type": "maps_search",
                                "rank_group": 3,
                                "rank_absolute": 4,
                                "place_id": "place-123",
                                "cid": "cid-123",
                                "title": "Clinic A",
                                "category": "Dentist",
                                "additional_categories": ["Dental clinic"],
                                "category_ids": ["dentist", "dental_clinic"],
                                "address": "1 Main St, Syracuse, NY 13202",
                                "address_info": {
                                    "address": "1 Main St",
                                    "city": "Syracuse",
                                    "zip": "13202",
                                    "region": "New York",
                                    "country_code": "US",
                                },
                                "latitude": 43.0,
                                "longitude": -76.1,
                                "phone": "+1 555 0100",
                                "domain": "example.com",
                                "url": "https://example.com",
                                "rating": {"value": 4.5, "votes_count": 20},
                            }
                        ],
                    }
                ],
            }
        ]
    }

    records = parse_maps_payload(
        payload,
        task_id="maps-task-123",
        query="dentist",
        requested_location="Syracuse_NY_M",
        retrieved_at_utc="2026-09-08T00:00:00+00:00",
    )

    assert len(records) == 1
    record = records[0]
    assert record["task_tag"] == "Syracuse_NY_M:maps:general:01"
    assert record["location_code"] == 1023416
    assert record["language_code"] == "en"
    assert record["result_datetime_utc"] == "2026-09-07 20:00:00 +00:00"
    assert record["rank_group"] == 3
    assert record["rank_absolute"] == 4
    assert record["category"] == "Dentist"
    assert json.loads(record["additional_categories_json"]) == ["Dental clinic"]
    assert json.loads(record["category_ids_json"]) == ["dentist", "dental_clinic"]
    assert record["country_code"] == "US"
    assert record["phone"] == "+1 555 0100"
    assert record["domain"] == "example.com"
    assert record["url"] == "https://example.com"
    assert record["place_id"] == "place-123"
    assert record["cid"] == "cid-123"


def test_parse_local_finder_payload_preserves_available_fields() -> None:
    payload = {
        "tasks": [
            {
                "id": "finder-task-123",
                "data": {"tag": "Malone_NY_S:local_finder:general:01"},
                "result": [
                    {
                        "location_code": 1023114,
                        "language_code": "en",
                        "datetime": "2026-09-07 20:05:00 +00:00",
                        "items": [
                            {
                                "type": "local_pack",
                                "rank_group": 1,
                                "rank_absolute": 1,
                                "cid": "cid-456",
                                "title": "Clinic B",
                                "description": "General dentistry",
                                "phone": "+1 555 0101",
                                "domain": "clinic.example",
                                "url": "https://clinic.example",
                                "booking_url": "https://clinic.example/book",
                                "is_paid": False,
                                "rating": {"value": 4.0, "votes_count": 10},
                            }
                        ],
                    }
                ],
            }
        ]
    }

    records = parse_local_finder_payload(
        payload,
        task_id="finder-task-123",
        query="family dentist",
        requested_location="Malone_NY_S",
        retrieved_at_utc="2026-09-08T00:00:00+00:00",
    )

    assert len(records) == 1
    record = records[0]
    assert record["task_tag"] == "Malone_NY_S:local_finder:general:01"
    assert record["location_code"] == 1023114
    assert record["language_code"] == "en"
    assert record["result_datetime_utc"] == "2026-09-07 20:05:00 +00:00"
    assert record["rank_group"] == 1
    assert record["rank_absolute"] == 1
    assert record["phone"] == "+1 555 0101"
    assert record["domain"] == "clinic.example"
    assert record["url"] == "https://clinic.example"
    assert record["booking_url"] == "https://clinic.example/book"
    assert record["is_paid"] is False
    assert record["place_id"] is None
    assert record["cid"] == "cid-456"


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
