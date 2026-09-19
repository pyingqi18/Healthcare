"""Tests for offline auditing and parsing of ZIP-filtered major metros."""

import json
from pathlib import Path

import pandas as pd
import pytest

from medical_ratings.major_metro_filtered_parse import (
    audit_and_parse_major_metro_filtered_pages,
)


def payload(tag: str, cid: str, zip_code: str) -> dict[str, object]:
    return {
        "tasks": [
            {
                "id": f"task-{cid}",
                "status_code": 20000,
                "cost": 0.01236,
                "data": {"tag": tag},
                "result": [
                    {
                        "total_count": 1,
                        "count": 1,
                        "offset_token": None,
                        "items": [
                            {
                                "type": "business_listing",
                                "cid": cid,
                                "place_id": f"place-{cid}",
                                "title": f"Clinic {cid}",
                                "category": "Dentist",
                                "category_ids": ["dentist"],
                                "address": f"1 Main St {zip_code}",
                                "address_info": {
                                    "address": "1 Main St",
                                    "city": "City",
                                    "zip": zip_code,
                                    "region": "State",
                                    "country_code": "US",
                                },
                                "latitude": 1.0,
                                "longitude": 2.0,
                                "rating": {"value": 4.5, "votes_count": 10},
                            }
                        ],
                    }
                ],
            }
        ]
    }


def inputs(tmp_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, Path]:
    groups = [
        ("LA_CA_L", 1, "90001", "la"),
        ("LA_CA_L", 2, "90001", "la"),
        ("NYC_NY_L", 1, "10001", "nyc"),
        ("NYC_NY_L", 2, "10001", "nyc"),
    ]
    plan_rows = []
    log_rows = []
    for market, group, zip_code, cid in groups:
        group_id = f"{market}:g{group:02d}"
        api_tag = f"business_listings_major_metro_zip_filtered:{group_id}"
        page_tag = f"{api_tag}:p01"
        regex = "^9[01][0-9]{3}$" if market == "LA_CA_L" else "^1[01][0-9]{3}$"
        raw_name = f"{market}_g{group:02d}.json"
        (tmp_path / raw_name).write_text(
            json.dumps(payload(api_tag, cid, zip_code)), encoding="utf-8"
        )
        plan_rows.append(
            {
                "group_id": group_id,
                "market": market,
                "category_group": group,
                "api_task_tag": api_tag,
                "filters_json": json.dumps(
                    [["address_info.zip", "regex", regex]], separators=(",", ":")
                ),
                "audited_total_count": 1,
                "planned_page_count": 1,
                "limit": 1000,
            }
        )
        log_rows.append(
            {
                "page_request_tag": page_tag,
                "group_id": group_id,
                "market": market,
                "category_group": group,
                "page_number": 1,
                "api_task_tag": api_tag,
                "request_status": "completed",
                "raw_file": raw_name,
                "retrieved_at_utc": "2026-09-19T00:00:00+00:00",
                "item_count": 1,
                "total_count": 1,
                "offset_token_used": None,
                "next_offset_token": None,
            }
        )
    return pd.DataFrame(log_rows), pd.DataFrame(plan_rows), tmp_path


def test_complete_filtered_pages_parse_and_deduplicate_by_market(
    tmp_path: Path,
) -> None:
    log, plan, raw = inputs(tmp_path)
    observations, candidates, group_audit, market_summary, summary = (
        audit_and_parse_major_metro_filtered_pages(log, plan, raw)
    )
    assert len(observations) == 4
    assert len(candidates) == 2
    assert group_audit["group_complete"].all()
    assert market_summary["unique_profile_candidates"].tolist() == [1, 1]
    assert summary["completed_pages_parsed"] == 4
    assert summary["cross_category_duplicate_observations_removed"] == 2
    assert summary["all_results_match_server_zip_filter"] is True
    assert summary["api_requests_submitted"] == 0


def test_filtered_parse_rejects_result_outside_zip_filter(tmp_path: Path) -> None:
    log, plan, raw = inputs(tmp_path)
    first = log.iloc[0]
    bad = payload(str(first["api_task_tag"]), "la", "92801")
    (raw / str(first["raw_file"])).write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="outside its ZIP filter"):
        audit_and_parse_major_metro_filtered_pages(log, plan, raw)
