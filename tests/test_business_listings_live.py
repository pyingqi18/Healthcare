"""Tests for paid gating, parsing, and deduplication of Business Listings."""

from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from medical_ratings.business_listings_live import (
    audit_business_listings_page_groups,
    business_listings_page_metadata,
    deduplicate_business_listings,
    parse_completed_business_listings_results,
    parse_business_listings_payload,
    validate_pilot_manifest,
)
from medical_ratings.dataforseo import DataForSEOClient


ROOT = Path(__file__).resolve().parents[1]


def sample_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_tag": f"business_listings_pilot:{market}:g{group:02d}",
                "market": market,
                "category_group": group,
                "categories": "dentist|dental_clinic" if group == 1 else "orthodontist",
                "category_count": 2 if group == 1 else 1,
                "location_coordinate": coordinate,
                "limit": 1000,
                "planning_only": True,
                "execution_enabled": False,
            }
            for market, coordinate in [
                ("Malone_NY_S", "44.8487,-74.2963,5"),
                ("Syracuse_NY_M", "43.0481,-76.1474,15"),
            ]
            for group in (1, 2)
        ]
    )


def sample_payload(tag: str, *, cid: str = "123", place_id: str = "place-1") -> dict[str, Any]:
    return {
        "status_code": 20000,
        "tasks_count": 1,
        "tasks_error": 0,
        "tasks": [
            {
                "id": "live-task-1",
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
                                "title": "Example Dental",
                                "category": "Dentist",
                                "category_ids": ["dentist"],
                                "additional_categories": ["Dental clinic"],
                                "cid": cid,
                                "place_id": place_id,
                                "address": "1 Main St, Malone, NY 12953",
                                "address_info": {
                                    "address": "1 Main St",
                                    "city": "Malone",
                                    "zip": "12953",
                                    "region": "New York",
                                    "country_code": "US",
                                },
                                "latitude": 44.85,
                                "longitude": -74.30,
                                "rating": {"value": 4.8, "votes_count": 25},
                            }
                        ]
                    }
                ],
            }
        ],
    }


def test_validate_pilot_manifest_requires_four_locked_requests() -> None:
    validated = validate_pilot_manifest(sample_manifest())
    assert len(validated) == 4
    with pytest.raises(ValueError, match="exactly four"):
        validate_pilot_manifest(sample_manifest().iloc[:3])


def test_client_posts_one_live_task_and_records_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DataForSEOClient("login", "password")
    captured: dict[str, Any] = {}
    tag = "business_listings_pilot:Malone_NY_S:g01"

    def fake_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        captured.update({"method": method, "url": url, **kwargs})
        return sample_payload(tag)

    monkeypatch.setattr(client, "_request", fake_request)
    payload, provenance = client.search_business_listings_live(
        url="https://api.dataforseo.com/v3/business_data/business_listings/search/live",
        categories=["dentist", "dental_clinic"],
        location_coordinate="44.8487000,-74.2963000,5",
        limit=1000,
        tag=tag,
        filters=[["address_info.zip", "regex", "^12953$"]],
    )
    assert captured["method"] == "POST"
    assert captured["json"][0]["categories"] == ["dentist", "dental_clinic"]
    assert captured["json"][0]["filters"] == [
        ["address_info.zip", "regex", "^12953$"]
    ]
    assert payload["tasks"][0]["data"]["tag"] == tag
    assert provenance["item_count"] == 1
    assert provenance["api_cost_usd"] == 0.01236
    assert provenance["filters"] == '[["address_info.zip","regex","^12953$"]]'
    assert len(provenance["params_hash"]) == 64


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update({"status_code": 20100}), "status 20000"),
        (
            lambda payload: payload["tasks"][0].update({"status_code": 20100}),
            "task was not completed",
        ),
        (
            lambda payload: payload["tasks"][0].update({"result": []}),
            "one result object",
        ),
        (
            lambda payload: payload["tasks"][0]["result"][0].update({"count": 2}),
            "count does not match",
        ),
    ],
)
def test_live_client_requires_completed_consistent_response(
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
    message: str,
) -> None:
    client = DataForSEOClient("login", "password")
    tag = "business_listings_rollout:Buffalo_NY_L:g01:p01"
    payload = sample_payload(tag)
    mutation(payload)
    monkeypatch.setattr(client, "_request", lambda *args, **kwargs: payload)
    with pytest.raises(RuntimeError, match=message):
        client.search_business_listings_live(
            url="https://example.test",
            categories=["dentist"],
            location_coordinate="42.8864,-78.8784,25",
            limit=1000,
            tag=tag,
        )


def test_client_rejects_more_than_ten_categories() -> None:
    client = DataForSEOClient("login", "password")
    with pytest.raises(ValueError, match="1 to 10"):
        client.search_business_listings_live(
            url="https://example.test",
            categories=[f"category_{index}" for index in range(11)],
            location_coordinate="44,-74,5",
            limit=1000,
            tag="pilot",
        )


def test_client_supports_offset_and_records_page_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DataForSEOClient("login", "password")
    tag = "rollout:NYC_NY_L:g01:p02"
    payload = sample_payload(tag)
    payload["tasks"][0]["result"][0].update(
        {"total_count": 1501, "count": 1, "offset_token": "next-page-token"}
    )
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return payload

    monkeypatch.setattr(client, "_request", fake_request)
    _, provenance = client.search_business_listings_live(
        url="https://example.test",
        categories=["dentist"],
        location_coordinate="40.7128,-74.0060,50",
        limit=1000,
        tag=tag,
        offset=1000,
    )
    assert captured["json"][0]["offset"] == 1000
    assert provenance["total_count"] == 1501
    assert provenance["next_offset_token"] == "next-page-token"
    assert provenance["page_has_more"] is True


def test_page_metadata_detects_truncated_saved_response() -> None:
    tag = "rollout:NYC_NY_L:g01:p01"
    payload = sample_payload(tag)
    payload["tasks"][0]["result"][0].update(
        {"total_count": 1200, "count": 1, "offset_token": "continue-token"}
    )
    metadata = business_listings_page_metadata(payload, expected_tag=tag)
    assert metadata["returned_item_count"] == 1
    assert metadata["pagination_required"] is True
    assert metadata["continuation_available"] is True


def test_group_audit_treats_contiguous_atlanta_pages_as_complete() -> None:
    pages = pd.DataFrame(
        {
            "market": ["Atlanta_GA_L"] * 4,
            "category_group": [1] * 4,
            "total_count": [3640] * 4,
            "returned_item_count": [1000, 1000, 1000, 640],
            "requested_offset": [0, 1000, 2000, 3000],
        }
    )
    groups = audit_business_listings_page_groups(pages)
    assert len(groups) == 1
    assert groups.loc[0, "saved_offsets"] == "0|1000|2000|3000"
    assert groups.loc[0, "covered_item_positions"] == 3640
    assert groups.loc[0, "missing_item_positions"] == 0
    assert bool(groups.loc[0, "category_group_complete"]) is True


def test_group_audit_detects_missing_middle_page() -> None:
    pages = pd.DataFrame(
        {
            "market": ["Atlanta_GA_L"] * 3,
            "category_group": [1] * 3,
            "total_count": [3640] * 3,
            "returned_item_count": [1000, 1000, 640],
            "requested_offset": [0, 2000, 3000],
        }
    )
    groups = audit_business_listings_page_groups(pages)
    assert groups.loc[0, "missing_item_positions"] == 1000
    assert bool(groups.loc[0, "gap_detected"]) is True
    assert bool(groups.loc[0, "category_group_complete"]) is False


def test_parser_preserves_identity_zip_category_and_rating() -> None:
    tag = "business_listings_pilot:Malone_NY_S:g01"
    records = parse_business_listings_payload(
        sample_payload(tag),
        expected_tag=tag,
        market="Malone_NY_S",
        retrieved_at_utc="2026-09-18T00:00:00Z",
    )
    assert len(records) == 1
    record = records[0]
    assert record["cid"] == "123"
    assert record["place_id"] == "place-1"
    assert record["zip"] == "12953"
    assert record["category"] == "Dentist"
    assert record["rating_value"] == 4.8


def test_parser_rejects_wrong_response_tag() -> None:
    with pytest.raises(ValueError, match="tag"):
        parse_business_listings_payload(
            sample_payload("actual"),
            expected_tag="expected",
            market="Malone_NY_S",
            retrieved_at_utc="2026-09-18T00:00:00Z",
        )


def test_rollout_parser_uses_all_audited_pages(tmp_path: Path) -> None:
    tags = [
        "business_listings_rollout:Atlanta_GA_L:g01:p01",
        "business_listings_rollout:Atlanta_GA_L:g01:p02",
    ]
    rows = []
    for index, tag in enumerate(tags, start=1):
        payload = sample_payload(tag, cid=str(index), place_id=f"place-{index}")
        raw_name = f"page-{index}.json"
        (tmp_path / raw_name).write_text(json.dumps(payload), encoding="utf-8")
        rows.append(
            {
                "task_tag": tag,
                "market": "Atlanta_GA_L",
                "request_status": "completed",
                "raw_file": raw_name,
                "retrieved_at_utc": "2026-09-19T00:00:00Z",
                "item_count": 1,
            }
        )
    observations = parse_completed_business_listings_results(
        pd.DataFrame(rows),
        tmp_path,
        markets={"Atlanta_GA_L"},
        expected_completed_requests=2,
    )
    assert len(observations) == 2
    assert set(observations["cid"].astype(str)) == {"1", "2"}


def test_rollout_parser_rejects_missing_audited_page(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="differs from the audited page count"):
        parse_completed_business_listings_results(
            pd.DataFrame(
                [
                    {
                        "task_tag": "business_listings_rollout:Atlanta_GA_L:g01:p01",
                        "market": "Atlanta_GA_L",
                        "request_status": "completed",
                        "raw_file": "page-1.json",
                        "retrieved_at_utc": "2026-09-19T00:00:00Z",
                        "item_count": 1,
                    }
                ]
            ),
            tmp_path,
            markets={"Atlanta_GA_L"},
            expected_completed_requests=2,
        )


def test_deduplication_links_category_observations_by_stable_ids() -> None:
    base = parse_business_listings_payload(
        sample_payload("tag-1"),
        expected_tag="tag-1",
        market="Malone_NY_S",
        retrieved_at_utc="2026-09-18T00:00:00Z",
    )[0]
    second = {**base, "task_tag": "tag-2", "category": "Dental clinic"}
    candidates = deduplicate_business_listings(pd.DataFrame([base, second]))
    assert len(candidates) == 1
    assert candidates.loc[0, "profile_key"] == "google:cid:123"
    assert candidates.loc[0, "observation_count"] == 2
    assert candidates.loc[0, "observed_categories"] == "Dental clinic|Dentist"


def test_validation_mode_does_not_read_credentials_or_call_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = ROOT / "scripts/scrape/01a_run_business_listings_pilot.py"
    spec = importlib.util.spec_from_file_location("business_listings_runner", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest_path = tmp_path / "manifest.csv"
    sample_manifest().to_csv(manifest_path, index=False)
    monkeypatch.setattr(
        module,
        "parse_arguments",
        lambda: Namespace(
            manifest=manifest_path,
            settings=ROOT / "config/settings.yaml",
            results_directory=tmp_path / "raw",
            confirm_submit=None,
        ),
    )
    monkeypatch.setattr(
        module,
        "require_dataforseo_credentials",
        lambda: (_ for _ in ()).throw(AssertionError("credentials were read")),
    )
    assert module.main() == 0


def test_confirmed_execution_reports_actual_requests_and_cost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script_path = ROOT / "scripts/scrape/01a_run_business_listings_pilot.py"
    spec = importlib.util.spec_from_file_location("business_listings_paid_runner", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest_path = tmp_path / "manifest.csv"
    sample_manifest().to_csv(manifest_path, index=False)
    results_directory = tmp_path / "raw"
    monkeypatch.setattr(
        module,
        "parse_arguments",
        lambda: Namespace(
            manifest=manifest_path,
            settings=ROOT / "config/settings.yaml",
            results_directory=results_directory,
            confirm_submit="SUBMIT_4_PAID_BUSINESS_LISTINGS_REQUESTS",
        ),
    )
    monkeypatch.setattr(module, "require_dataforseo_credentials", lambda: ("login", "password"))
    monkeypatch.setattr(module.time, "sleep", lambda _: None)

    class FakeClient:
        def __init__(self, login: str, password: str) -> None:
            assert (login, password) == ("login", "password")

        def search_business_listings_live(self, **kwargs: Any):
            tag = kwargs["tag"]
            return sample_payload(tag), {
                "task_tag": tag,
                "task_id": f"task-{tag}",
                "api_type": "business_listings_live",
                "endpoint": kwargs["url"],
                "location_coordinate": kwargs["location_coordinate"],
                "categories": "|".join(kwargs["categories"]),
                "category_count": len(kwargs["categories"]),
                "limit": kwargs["limit"],
                "params_hash": "a" * 64,
                "retrieved_at_utc": "2026-09-18T00:00:00Z",
                "api_status_code": 20000,
                "api_status_message": "Ok.",
                "api_cost_usd": 0.01236,
                "item_count": 1,
                "request_status": "completed",
            }

    monkeypatch.setattr(module, "DataForSEOClient", FakeClient)
    assert module.main() == 0
    output = capsys.readouterr().out
    assert '"credentials_read": true' in output
    assert '"api_requests_submitted": 4' in output
    assert '"api_cost_usd": 0.04944' in output
    assert len(list((results_directory / "raw").glob("*.json"))) == 4


def test_existing_unlogged_raw_response_blocks_paid_resubmission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = ROOT / "scripts/scrape/01a_run_business_listings_pilot.py"
    spec = importlib.util.spec_from_file_location("business_listings_resume_guard", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest_path = tmp_path / "manifest.csv"
    manifest = sample_manifest()
    manifest.to_csv(manifest_path, index=False)
    results_directory = tmp_path / "raw"
    raw_directory = results_directory / "raw"
    raw_directory.mkdir(parents=True)
    first_tag = str(manifest.loc[0, "task_tag"])
    (raw_directory / module.safe_raw_name(first_tag)).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        module,
        "parse_arguments",
        lambda: Namespace(
            manifest=manifest_path,
            settings=ROOT / "config/settings.yaml",
            results_directory=results_directory,
            confirm_submit="SUBMIT_4_PAID_BUSINESS_LISTINGS_REQUESTS",
        ),
    )
    monkeypatch.setattr(module, "require_dataforseo_credentials", lambda: ("login", "password"))
    monkeypatch.setattr(module, "DataForSEOClient", lambda *_: object())
    with pytest.raises(RuntimeError, match="Refusing to resubmit"):
        module.main()
