"""Offline tests for safe resumable Google Reviews submission."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_script():
    path = PROJECT_ROOT / "scripts" / "scrape" / "21_submit_review_collection.py"
    spec = importlib.util.spec_from_file_location("submit_reviews", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["submit_reviews"] = module
    spec.loader.exec_module(module)
    return module


def make_manifest(size: int = 9) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_tag": f"reviews:cid:{cid}",
                "final_physical_location_id": f"location:{cid}",
                "clinic_key": f"google:cid:{cid}",
                "cid": str(cid),
                "place_id": f"place-{cid}",
                "identifier_type": "place_id",
                "identifier_value": f"place-{cid}",
                "requested_location": "Syracuse_NY_M",
                "location_code": 1023416,
                "language_code": "en",
                "sort_by": "newest",
                "planned_depth": 20,
                "estimated_maximum_cost_usd": 0.0015,
            }
            for cid in range(1, size + 1)
        ]
    )


def test_validate_manifest_and_configured_batch_sizes() -> None:
    module = load_script()
    manifest = make_manifest()

    module.validate_manifest(manifest)
    grouped = module.batches(manifest.to_dict(orient="records"), 50)

    assert [len(group) for group in grouped] == [9]


def test_validate_manifest_accepts_nonlegacy_task_count() -> None:
    module = load_script()

    module.validate_manifest(make_manifest(3))


def test_load_submitted_tags_keeps_successes_and_allows_retry(
    tmp_path: Path,
) -> None:
    module = load_script()
    path = tmp_path / "review_task_log.csv"
    pd.DataFrame(
        [
            {"task_tag": "reviews:cid:1", "submission_status": "submitted"},
            {"task_tag": "reviews:cid:2", "submission_status": "failed"},
        ]
    ).to_csv(path, index=False)

    assert module.load_submitted_tags(
        path, {"reviews:cid:1", "reviews:cid:2"}
    ) == {"reviews:cid:1"}


def test_validate_manifest_rejects_identifier_drift() -> None:
    module = load_script()
    manifest = make_manifest()
    manifest.loc[0, "identifier_value"] = "different-place"

    try:
        module.validate_manifest(manifest)
    except ValueError as error:
        assert "does not match" in str(error)
    else:
        raise AssertionError("Expected identifier drift to fail")


def test_validate_manifest_allows_multiple_profiles_per_physical_location() -> None:
    module = load_script()
    manifest = make_manifest(2)
    manifest["final_physical_location_id"] = "location:shared"
    manifest["competition_location_id"] = "location:shared"
    manifest["outcome_profile_key"] = manifest["clinic_key"]

    module.validate_manifest(manifest)
