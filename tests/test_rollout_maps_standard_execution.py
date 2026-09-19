"""Tests for the uniform Maps Standard paid execution boundary."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/scrape/18a_submit_rollout_maps_supplement.py"
SPEC = importlib.util.spec_from_file_location("maps_standard_submit", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def manifest() -> pd.DataFrame:
    rows = []
    for market_index in range(15):
        for keyword in ["dentist", "dental clinic"]:
            rows.append({
                "task_tag": f"tag:{market_index}:{keyword}",
                "plan_type": "market_core_discovery",
                "market": f"Market_{market_index}",
                "query": keyword,
                "location_code": 1000 + market_index,
                "language_code": "en",
                "depth": 100,
                "priority": 1,
                "included_in_main_discovery_pipeline": True,
            })
    return pd.DataFrame(rows)


def test_uniform_manifest_accepts_thirty_tasks_for_fifteen_markets() -> None:
    MODULE.validate_manifest(
        manifest(), {f"Market_{index}" for index in range(15)}
    )


def test_uniform_manifest_rejects_legacy_reference_query() -> None:
    frame = manifest()
    frame.loc[0, "plan_type"] = "unmatched_reference_verification"
    with pytest.raises(ValueError, match="non-discovery"):
        MODULE.validate_manifest(
            frame, {f"Market_{index}" for index in range(15)}
        )
