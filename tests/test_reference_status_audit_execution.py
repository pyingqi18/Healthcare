from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from medical_ratings.reference_status_audit_execution import (
    pending_reference_status_tasks,
    submitted_reference_status_tasks,
    validate_reference_status_audit_manifest,
)


def manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_tag": f"reference_status_audit:Market_{index}:abc{index}",
                "plan_type": "historical_reference_status_audit",
                "market": f"Market_{index}",
                "reference_key": f"competition_unit:{index}",
                "query": f"Dental Practice {index} {index} Main St",
                "location_code": 1000 + index,
                "language_code": "en",
                "depth": 100,
                "priority": 1,
                "estimated_cost_usd": 0.0006,
                "included_in_main_discovery_pipeline": False,
                "planning_only": True,
                "execution_enabled": False,
            }
            for index in range(2)
        ]
    )


def summary() -> dict[str, object]:
    return {
        "analysis_status": "post_adjudication_gap_closure_planning_only",
        "planning_only": True,
        "reference_status_audit_tasks": 2,
        "reference_status_audit_markets": ["Market_0", "Market_1"],
        "reference_status_audit_estimated_cost_usd": 0.0012,
    }


def task_log() -> pd.DataFrame:
    frame = manifest().loc[
        :, ["task_tag", "market", "reference_key", "query"]
    ].copy()
    frame["task_id"] = ["task-0", "task-1"]
    frame["submission_status"] = "submitted"
    return frame


def test_manifest_preserves_targeted_audit_boundary() -> None:
    validated = validate_reference_status_audit_manifest(manifest(), summary())
    assert len(validated) == 2
    assert validated["included_in_main_discovery_pipeline"].eq(False).all()
    assert validated["planning_only"].all()
    assert validated["execution_enabled"].eq(False).all()


def test_manifest_rejects_status_query_as_main_discovery() -> None:
    frame = manifest()
    frame.loc[0, "included_in_main_discovery_pipeline"] = True
    with pytest.raises(ValueError, match="cannot enter main discovery"):
        validate_reference_status_audit_manifest(frame, summary())


def test_submitted_tasks_reject_identity_drift() -> None:
    log = task_log()
    log.loc[0, "reference_key"] = "competition_unit:changed"
    with pytest.raises(ValueError, match="changed reference_key"):
        submitted_reference_status_tasks(log, manifest())


def test_pending_tasks_use_saved_task_ids(tmp_path: Path) -> None:
    submitted = submitted_reference_status_tasks(task_log(), manifest())
    (tmp_path / "task-0.json").write_text("{}", encoding="utf-8")
    pending = pending_reference_status_tasks(submitted, tmp_path)
    assert pending["task_id"].tolist() == ["task-1"]
