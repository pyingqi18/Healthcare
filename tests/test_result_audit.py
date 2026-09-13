"""Unit tests for aggregate clinic-search result audits."""

from medical_ratings.result_audit import audit_location_results


def test_audit_location_results_counts_coverage_without_names() -> None:
    maps_payload = {
        "tasks": [
            {
                "result": [
                    {
                        "items": [
                            {
                                "type": "maps_search",
                                "cid": "101",
                                "place_id": "place-101",
                                "title": "Clinic A",
                                "address": "1 Main St",
                                "address_info": {"zip": "13202"},
                                "latitude": 43.0,
                                "longitude": -76.1,
                                "rating": {"value": 4.5, "votes_count": 20},
                            },
                            {
                                "type": "maps_search",
                                "cid": "101",
                                "title": "Clinic A",
                            },
                        ]
                    }
                ]
            }
        ]
    }
    finder_payload = {
        "tasks": [
            {
                "result": [
                    {
                        "items": [
                            {
                                "type": "local_pack",
                                "cid": "202",
                                "title": "Clinic B",
                                "phone": "+1 555 0100",
                                "rating": {"value": 4.0},
                            }
                        ]
                    }
                ]
            }
        ]
    }

    summary = audit_location_results(
        [
            {
                "api_type": "maps",
                "region_key": "Syracuse_NY_M",
                "payload": maps_payload,
            },
            {
                "api_type": "local_finder",
                "region_key": "Malone_NY_S",
                "payload": finder_payload,
            },
        ]
    )

    assert summary["result_tasks"] == 2
    assert summary["result_items"] == 3
    assert summary["identifiers"] == {
        "unique_cid": 2,
        "unique_place_id": 1,
        "unique_stable_ids": 2,
        "items_without_cid_or_place_id": 0,
        "repeated_observations": 1,
    }
    assert summary["field_coverage_by_api"]["maps"]["cid"] == {
        "present": 2,
        "total": 2,
        "percent": 100.0,
    }
    assert summary["field_coverage_by_api"]["local_finder"]["place_id"][
        "percent"
    ] == 0.0
    assert "Clinic A" not in str(summary)


def test_audit_location_results_accepts_no_items() -> None:
    summary = audit_location_results(
        [
            {
                "api_type": "maps",
                "region_key": "Syracuse_NY_M",
                "payload": {"tasks": [{"result": [{"items": []}]}]},
            }
        ]
    )

    assert summary["result_tasks"] == 1
    assert summary["result_items"] == 0
    assert summary["field_coverage_by_api"]["maps"]["cid"]["percent"] == 0.0
