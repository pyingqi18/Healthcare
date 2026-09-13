"""Offline tests for resumable Business Info result downloads."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_script():
    path = PROJECT_ROOT / "scripts" / "scrape" / "12_download_business_info_results.py"
    spec = importlib.util.spec_from_file_location("download_business_info", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["download_business_info"] = module
    spec.loader.exec_module(module)
    return module


def make_task_log(size: int = 769) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_tag": f"business_info:cid:{cid}",
                "task_id": f"task-{cid}",
                "clinic_key": f"google:cid:{cid}",
                "cid": str(cid),
                "query": f"cid:{cid}",
                "submission_status": "submitted",
            }
            for cid in range(1, size + 1)
        ]
    )


def test_build_download_plan_requires_all_tasks_and_resumes(tmp_path: Path) -> None:
    module = load_script()
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "task-1.json").write_text("{}", encoding="utf-8")

    plan = module.build_download_plan(make_task_log(), raw)

    assert len(plan) == 769
    assert int(plan["already_downloaded"].sum()) == 1
    assert bool(plan.loc[plan["task_id"].eq("task-1"), "already_downloaded"].iloc[0])


def test_summarize_task_payload_validates_cid_and_counts_items() -> None:
    module = load_script()
    payload = {
        "status_code": 20000,
        "tasks": [
            {
                "id": "task-1",
                "status_code": 20000,
                "result": [
                    {
                        "keyword": "cid:123",
                        "items": [{"type": "google_business_info", "cid": "123"}],
                    }
                ],
            }
        ],
    }

    summary = module.summarize_task_payload(
        payload,
        expected_task_id="task-1",
        expected_cid="123",
    )

    assert summary["result_ready"] is True
    assert summary["item_count"] == 1


def test_summarize_task_payload_rejects_wrong_cid() -> None:
    module = load_script()
    payload = {
        "status_code": 20000,
        "tasks": [
            {
                "id": "task-1",
                "status_code": 20000,
                "result": [
                    {"keyword": "cid:123", "items": [{"cid": "999"}]}
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match="different"):
        module.summarize_task_payload(
            payload,
            expected_task_id="task-1",
            expected_cid="123",
        )


def test_write_json_atomic_creates_valid_json(tmp_path: Path) -> None:
    module = load_script()
    target = tmp_path / "raw" / "task.json"

    module.write_json_atomic(target, {"status_code": 20000})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "status_code": 20000
    }
    assert not target.with_suffix(".json.tmp").exists()
