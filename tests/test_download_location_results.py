"""Offline tests for resumable clinic-search result downloads."""

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
        / "04_download_location_results.py"
    )
    spec = importlib.util.spec_from_file_location(
        "download_location_results",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_download_plan_filters_failed_and_resumes(
    tmp_path: Path,
) -> None:
    module = load_script()
    raw_directory = tmp_path / "raw"
    raw_directory.mkdir()
    (raw_directory / "task-new.json").write_text("{}", encoding="utf-8")

    task_log = pd.DataFrame(
        [
            {
                "task_tag": "tag-1",
                "task_id": "task-failed",
                "api_type": "maps",
                "query": "dentist",
                "region_key": "Malone_NY_S",
                "submission_status": "failed",
            },
            {
                "task_tag": "tag-1",
                "task_id": "task-old",
                "api_type": "maps",
                "query": "dentist",
                "region_key": "Malone_NY_S",
                "submission_status": "submitted",
            },
            {
                "task_tag": "tag-1",
                "task_id": "task-new",
                "api_type": "maps",
                "query": "dentist",
                "region_key": "Malone_NY_S",
                "submission_status": "submitted",
            },
        ]
    )

    plan = module.build_download_plan(task_log, raw_directory)

    assert len(plan) == 1
    assert plan.loc[0, "task_id"] == "task-new"
    assert bool(plan.loc[0, "already_downloaded"]) is True


def test_summarize_task_payload_counts_items() -> None:
    module = load_script()
    payload = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {"items": [{"title": "A"}, {"title": "B"}]},
                    {"items": [{"title": "C"}]},
                ],
            }
        ],
    }

    summary = module.summarize_task_payload(payload)

    assert summary["result_ready"] is True
    assert summary["result_blocks"] == 2
    assert summary["item_count"] == 3


def test_write_json_atomic_creates_valid_json(tmp_path: Path) -> None:
    module = load_script()
    target = tmp_path / "raw" / "task-id.json"

    module.write_json_atomic(target, {"status_code": 20000})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "status_code": 20000
    }
    assert not target.with_suffix(".json.tmp").exists()


def test_build_download_plan_rejects_missing_columns(
    tmp_path: Path,
) -> None:
    module = load_script()

    with pytest.raises(KeyError, match="missing columns"):
        module.build_download_plan(
            pd.DataFrame([{"task_id": "task-id"}]),
            tmp_path,
        )
