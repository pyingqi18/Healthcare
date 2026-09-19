"""Offline tests for resumable Google Reviews result downloads."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_script():
    path = PROJECT_ROOT / "scripts" / "scrape" / "22_download_review_results.py"
    spec = importlib.util.spec_from_file_location("download_reviews", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["download_reviews"] = module
    spec.loader.exec_module(module)
    return module


def make_task_log(size: int = 5) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_tag": f"reviews:cid:{cid}",
                "task_id": f"task-{cid}",
                "final_physical_location_id": f"location:{cid}",
                "clinic_key": f"google:cid:{cid}",
                "cid": str(cid),
                "place_id": f"place-{cid}",
                "identifier_type": "place_id",
                "identifier_value": f"place-{cid}",
                "requested_location": "Syracuse_NY_M",
                "planned_depth": 20,
                "submission_status": "submitted",
            }
            for cid in range(1, size + 1)
        ]
    )


def test_build_download_plan_derives_task_count_and_resumes(
    tmp_path: Path,
) -> None:
    module = load_script()
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "task-1.json").write_text("{}", encoding="utf-8")

    plan = module.build_download_plan(make_task_log(), raw)

    assert len(plan) == 5
    assert int(plan["already_downloaded"].sum()) == 1


def test_review_payload_validates_identity_and_flags_incomplete_depth() -> None:
    module = load_script()
    payload = {
        "status_code": 20000,
        "tasks": [
            {
                "id": "task-1",
                "status_code": 20000,
                "data": {"tag": "reviews:cid:1"},
                "result": [
                    {
                        "place_id": "place-1",
                        "reviews_count": 50,
                        "items": [{"review_id": str(i)} for i in range(20)],
                    }
                ],
            }
        ],
    }

    summary = module.summarize_review_payload(
        payload,
        expected_task_id="task-1",
        expected_task_tag="reviews:cid:1",
        expected_identifier_type="place_id",
        expected_identifier_value="place-1",
        planned_depth=20,
    )

    assert summary["result_ready"] is True
    assert summary["item_count"] == 20
    assert summary["business_reviews_count"] == 50
    assert summary["needs_depth_followup"] is True


def test_review_payload_accepts_not_ready_result() -> None:
    module = load_script()
    payload = {
        "status_code": 20000,
        "tasks": [
            {
                "id": "task-1",
                "status_code": 20100,
                "data": {"tag": "reviews:cid:1"},
                "result": None,
            }
        ],
    }

    summary = module.summarize_review_payload(
        payload,
        expected_task_id="task-1",
        expected_task_tag="reviews:cid:1",
        expected_identifier_type="place_id",
        expected_identifier_value="place-1",
        planned_depth=20,
    )

    assert summary["result_ready"] is False
    assert summary["needs_depth_followup"] is False


def test_review_payload_rejects_wrong_place_id() -> None:
    module = load_script()
    payload = {
        "status_code": 20000,
        "tasks": [
            {
                "id": "task-1",
                "data": {"tag": "reviews:cid:1"},
                "result": [{"place_id": "wrong-place", "items": []}],
            }
        ],
    }

    with pytest.raises(ValueError, match="identifier"):
        module.summarize_review_payload(
            payload,
            expected_task_id="task-1",
            expected_task_tag="reviews:cid:1",
            expected_identifier_type="place_id",
            expected_identifier_value="place-1",
            planned_depth=20,
        )


def test_write_json_atomic_creates_valid_json(tmp_path: Path) -> None:
    module = load_script()
    target = tmp_path / "raw" / "task.json"

    module.write_json_atomic(target, {"status_code": 20000})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "status_code": 20000
    }
    assert not target.with_suffix(".json.tmp").exists()
