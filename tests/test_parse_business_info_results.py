"""Offline tests for batch parsing downloaded Business Info results."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
                        "items": [
                            {
                                "type": "google_business_info",
                                "cid": "123",
                                "place_id": "place-123",
                                "title": "Clinic A",
                                "category": "Dentist",
                                "address_info": {"zip": "13202"},
                            }
                        ],
                    }
                ],
            }
        ]
    }


def load_script():
    path = PROJECT_ROOT / "scripts" / "scrape" / "13_parse_business_info_results.py"
    spec = importlib.util.spec_from_file_location("parse_business_info", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["parse_business_info"] = module
    spec.loader.exec_module(module)
    return module


def result_log() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_id": "task-123",
                "task_tag": "business_info:cid:123",
                "cid": "123",
                "query": "cid:123",
                "download_status": "downloaded",
                "retrieved_at_utc": "2026-09-08T03:05:00+00:00",
                "item_count": 1,
            }
        ]
    )


def test_parse_downloaded_business_info_validates_and_parses(tmp_path: Path) -> None:
    module = load_script()
    raw = tmp_path / "raw"
    raw.mkdir()
    raw_payload = payload()
    raw_payload["tasks"][0]["id"] = "task-123"
    (raw / "task-123.json").write_text(
        json.dumps(raw_payload), encoding="utf-8"
    )

    profiles = module.parse_downloaded_business_info(result_log(), raw)

    assert len(profiles) == 1
    assert profiles.loc[0, "cid"] == "123"
    assert profiles.loc[0, "place_id"] == "place-123"


def test_parse_downloaded_business_info_rejects_wrong_tag(tmp_path: Path) -> None:
    module = load_script()
    raw = tmp_path / "raw"
    raw.mkdir()
    raw_payload = payload()
    raw_payload["tasks"][0]["data"]["tag"] = "wrong-tag"
    (raw / "task-123.json").write_text(
        json.dumps(raw_payload), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Task tag mismatch"):
        module.parse_downloaded_business_info(result_log(), raw)
