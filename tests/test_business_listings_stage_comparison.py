"""Tests for batch eligibility and recall comparison across rollout markets."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/scrape/16a_audit_business_listings_rollout_stage.py"
SPEC = importlib.util.spec_from_file_location(
    "business_listings_stage_comparison", SCRIPT
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def candidates() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "requested_location": [f"Market_{index:02d}" for index in range(10)],
            "profile_key": [f"profile:{index}" for index in range(10)],
        }
    )


def result_log() -> pd.DataFrame:
    rows = [
        {
            "task_tag": f"rollout:Market_{index:02d}:g01:p01",
            "stage": "standard_rollout",
            "market": f"Market_{index:02d}",
            "request_status": "completed",
        }
        for index in range(10)
    ]
    rows.append(
        {
            "task_tag": "rollout:Atlanta:g01:p01",
            "stage": "large_market_validation",
            "market": "Atlanta_GA_L",
            "request_status": "completed",
        }
    )
    return pd.DataFrame(rows)


def recall_gate() -> dict[str, float]:
    return {
        "approve_primary_overall_minimum": 0.95,
        "approve_primary_each_market_minimum": 0.90,
        "supplement_overall_minimum": 0.90,
        "reject_each_market_below": 0.80,
    }


def test_select_stage_markets_requires_the_exact_candidate_market_set() -> None:
    selected = MODULE.select_stage_markets(
        candidates(), result_log(), stage="standard_rollout"
    )
    assert selected == [f"Market_{index:02d}" for index in range(10)]


def test_select_stage_markets_rejects_missing_candidate_market() -> None:
    with pytest.raises(ValueError, match="Candidate markets differ"):
        MODULE.select_stage_markets(
            candidates().iloc[:-1].copy(),
            result_log(),
            stage="standard_rollout",
        )


def test_stage_recall_is_weighted_by_reference_locations() -> None:
    market_summaries = pd.DataFrame(
        {
            "market": ["small", "large"],
            "completed_paid_requests": [2, 2],
            "actual_api_cost_usd": [0.1, 0.2],
            "raw_items_reported": [10, 30],
            "unique_profile_candidates": [8, 20],
            "eligible_target_zip_profiles": [5, 15],
            "outside_target_zip_profiles": [3, 5],
            "missing_zip_profiles": [0, 0],
            "non_us_postal_profiles": [0, 1],
            "unrecognized_postal_profiles": [0, 0],
            "provisional_included_profiles": [5, 15],
            "manual_category_review_profiles": [0, 0],
            "excluded_category_profiles": [0, 0],
            "decision": ["approve_as_primary", "reject_or_redesign"],
        }
    )
    matches = pd.DataFrame(
        {
            "reference_key": ["s1", "l1", "l2", "l3"],
            "market": ["small", "large", "large", "large"],
            "discovered": [True, True, False, False],
        }
    )
    _, summary = MODULE.build_stage_summary(
        market_summaries,
        matches,
        recall_gate(),
        stage="standard_rollout",
    )
    assert summary["reference_recall"]["overall_recall"] == 0.5
    assert summary["reference_recall"]["minimum_market_recall"] == 1 / 3
    assert summary["reference_recall"]["decision"] == "reject_or_redesign"
