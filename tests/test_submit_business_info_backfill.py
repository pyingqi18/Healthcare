"""Offline tests for resumable Business Info submission helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_script():
    path = PROJECT_ROOT / "scripts" / "scrape" / "11_submit_business_info_backfill.py"
    spec = importlib.util.spec_from_file_location("submit_business_info", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["submit_business_info"] = module
    spec.loader.exec_module(module)
    return module


def make_manifest(size: int = 7) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_tag": f"business_info:cid:{cid}",
                "clinic_key": f"google:cid:{cid}",
                "cid": str(cid),
                "query": f"cid:{cid}",
                "location_code": 2840,
                "language_code": "en",
                "priority": 1,
                "estimated_unit_cost_usd": 0.0015,
            }
            for cid in range(1, size + 1)
        ]
    )


def test_validate_manifest_and_batch_sizes() -> None:
    module = load_script()
    manifest = make_manifest(205)

    module.validate_manifest(manifest)
    grouped = module.batches(manifest.to_dict(orient="records"))

    assert len(grouped) == 3
    assert [len(group) for group in grouped] == [100, 100, 5]


def test_validate_manifest_accepts_nonlegacy_task_count() -> None:
    module = load_script()

    module.validate_manifest(make_manifest(7))


def test_load_submitted_tags_keeps_only_successes(tmp_path: Path) -> None:
    module = load_script()
    path = tmp_path / "task_log.csv"
    pd.DataFrame(
        [
            {"task_tag": "tag-1", "submission_status": "submitted"},
            {"task_tag": "tag-2", "submission_status": "failed"},
        ]
    ).to_csv(path, index=False)

    assert module.load_submitted_tags(path) == {"tag-1"}


def test_load_submitted_tags_rejects_another_run(tmp_path: Path) -> None:
    module = load_script()
    path = tmp_path / "task_log.csv"
    pd.DataFrame(
        [{"task_tag": "foreign", "submission_status": "submitted"}]
    ).to_csv(path, index=False)

    try:
        module.load_submitted_tags(path, {"expected"})
    except ValueError as error:
        assert "outside this manifest" in str(error)
    else:
        raise AssertionError("Expected a foreign task log to fail")
