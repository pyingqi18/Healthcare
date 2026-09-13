"""Tests for clinic-search candidate overlap and keyword audits."""

import pandas as pd

from medical_ratings.candidate_audit import audit_search_candidates


def test_audit_search_candidates_reports_overlap_and_keyword_yield() -> None:
    observations = pd.DataFrame(
        [
            {
                "cid": "1",
                "source_api": "maps",
                "requested_location": "Syracuse_NY_M",
                "task_tag": "syracuse:maps:general:01",
                "query": "dentist",
                "zip": "13202",
                "category": "Dentist",
            },
            {
                "cid": "1",
                "source_api": "local_finder",
                "requested_location": "Syracuse_NY_M",
                "task_tag": "syracuse:finder:general:01",
                "query": "dentist",
                "zip": None,
                "category": None,
            },
            {
                "cid": "2",
                "source_api": "local_finder",
                "requested_location": "Malone_NY_S",
                "task_tag": "malone:finder:general:02",
                "query": "dental clinic+family dentist",
                "zip": None,
                "category": None,
            },
            {
                "cid": "3",
                "source_api": "maps",
                "requested_location": "Malone_NY_S",
                "task_tag": "malone:maps:general:01",
                "query": "dentist",
                "zip": "99999",
                "category": "Store",
            },
            {
                "cid": "3",
                "source_api": "maps",
                "requested_location": "Syracuse_NY_M",
                "task_tag": "syracuse:maps:general:02",
                "query": "dental clinic+family dentist",
                "zip": "99999",
                "category": "Store",
            },
        ]
    )
    regions = {
        "Malone_NY_S": {"zip_values": [12953]},
        "Syracuse_NY_M": {"zip_ranges": [[13200, 13299]]},
    }

    summary = audit_search_candidates(observations, regions)

    assert summary["unique_cid"] == 3
    assert summary["api_identifier_overlap"] == {
        "maps_unique_cid": 2,
        "local_finder_unique_cid": 2,
        "both_apis": 1,
        "maps_only": 1,
        "local_finder_only": 1,
    }
    assert summary["cross_region_overlap"] == {
        "Malone_NY_S__and__Syracuse_NY_M": 1,
    }
    assert summary["maps_geography"]["in_target_zip_scope"] == 1
    assert summary["maps_geography"]["outside_target_zip_scope"] == 1
    assert summary["keyword_efficiency"]["all"] == {
        "tasks": 5,
        "unique_cid": 3,
        "singleton_unique_cid": 2,
        "combination_only_unique_cid": 1,
    }
    assert summary["top_maps_categories"] == {
        "Store": 2,
        "Dentist": 1,
    }
