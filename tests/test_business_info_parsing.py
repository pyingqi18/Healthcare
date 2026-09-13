"""Tests for Google Business Info item parsing."""

import json

from medical_ratings.parsing import parse_business_info_payload


def payload() -> dict[str, object]:
    return {
        "tasks": [
            {
                "data": {"tag": "business_info:cid:123"},
                "result": [
                    {
                        "keyword": "cid:123",
                        "location_code": 2840,
                        "language_code": "en",
                        "datetime": "2026-09-08 03:00:00 +00:00",
                        "items": [
                            {
                                "type": "google_business_info",
                                "cid": "123",
                                "place_id": "place-123",
                                "title": "Clinic A",
                                "category": "Dentist",
                                "category_ids": ["dentist"],
                                "additional_categories": ["Cosmetic dentist"],
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
                                "rating": {"value": 4.5, "votes_count": 20},
                                "rating_distribution": {"5": 18},
                                "work_time": {"current_status": "opened"},
                            }
                        ],
                    }
                ],
            }
        ]
    }


def test_parse_business_info_payload_preserves_profile_and_provenance() -> None:
    records = parse_business_info_payload(
        payload(),
        task_id="task-123",
        query="cid:123",
        retrieved_at_utc="2026-09-08T03:05:00+00:00",
    )

    assert len(records) == 1
    record = records[0]
    assert record["task_tag"] == "business_info:cid:123"
    assert record["source_api"] == "google_my_business_info"
    assert record["cid"] == "123"
    assert record["zip"] == "13202"
    assert record["rating_5_star"] == 18
    assert record["current_status"] == "opened"
    assert json.loads(record["additional_categories_json"]) == [
        "Cosmetic dentist"
    ]
