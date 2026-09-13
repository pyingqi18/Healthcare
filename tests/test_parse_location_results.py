"""Offline tests for batch parsing downloaded clinic-search results."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_script() -> ModuleType:
    path = (
        PROJECT_ROOT
        / "scripts"
        / "scrape"
        / "06_parse_location_results.py"
    )
    spec = importlib.util.spec_from_file_location(
        "parse_location_results",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def maps_payload(tag: str) -> dict[str, object]:
    return {
        "tasks": [
            {
                "data": {"tag": tag},
                "result": [
                    {
                        "location_code": 1023416,
                        "language_code": "en",
                        "datetime": "2026-09-07 20:00:00 +00:00",
                        "items": [
                            {
                                "type": "maps_search",
                                "rank_absolute": 1,
                                "cid": "cid-1",
                                "place_id": "place-1",
                                "title": "Clinic A",
                                "category": "Dentist",
                                "address": "1 Main St",
                                "address_info": {"zip": "13202"},
                            }
                        ],
                    }
                ],
            }
        ]
    }


def result_log(tag: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_id": "task-1",
                "task_tag": tag,
                "api_type": "maps",
                "query": "dentist",
                "region_key": "Syracuse_NY_M",
                "download_status": "downloaded",
                "retrieved_at_utc": "2026-09-08T00:00:00+00:00",
                "item_count": 1,
            }
        ]
    )


def test_parse_downloaded_results_preserves_all_observations(
    tmp_path: Path,
) -> None:
    module = load_script()
    raw_directory = tmp_path / "raw"
    raw_directory.mkdir()
    tag = "Syracuse_NY_M:maps:general:01"
    (raw_directory / "task-1.json").write_text(
        json.dumps(maps_payload(tag)),
        encoding="utf-8",
    )

    observations = module.parse_downloaded_results(
        result_log(tag),
        raw_directory,
    )

    assert len(observations) == 1
    assert observations.loc[0, "task_id"] == "task-1"
    assert observations.loc[0, "task_tag"] == tag
    assert observations.loc[0, "source_api"] == "maps"
    assert observations.loc[0, "requested_location"] == "Syracuse_NY_M"
    assert observations.loc[0, "location_code"] == 1023416
    assert observations.loc[0, "cid"] == "cid-1"
    assert observations.loc[0, "place_id"] == "place-1"


def test_parse_downloaded_results_rejects_task_tag_mismatch(
    tmp_path: Path,
) -> None:
    module = load_script()
    raw_directory = tmp_path / "raw"
    raw_directory.mkdir()
    log_tag = "Syracuse_NY_M:maps:general:01"
    raw_tag = "Syracuse_NY_M:maps:general:02"
    (raw_directory / "task-1.json").write_text(
        json.dumps(maps_payload(raw_tag)),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Task tag mismatch"):
        module.parse_downloaded_results(
            result_log(log_tag),
            raw_directory,
        )
