"""Tests for no-cost rollout Maps supplement planning."""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/scrape/17a_plan_rollout_maps_supplement.py"
SPEC = importlib.util.spec_from_file_location("rollout_maps_plan", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_yaml_date_is_converted_before_json_serialization() -> None:
    summary = {"pricing_verified_on": MODULE._json_text(date(2026, 9, 18))}
    assert json.loads(json.dumps(summary))["pricing_verified_on"] == "2026-09-18"


def test_gap_audit_flags_close_identity_without_automatic_match() -> None:
    gaps = MODULE.audit_recall_gaps(
        pd.DataFrame(
            [
                {
                    "reference_key": "ref-1",
                    "market": "Market_A",
                    "reference_title": "Example Dental",
                    "reference_address": "1 Main St",
                    "discovered": False,
                    "best_candidate_key": "candidate-1",
                    "best_distance_meters": 25,
                    "best_title_similarity": 0.95,
                }
            ]
        )
    )
    assert gaps.loc[0, "gap_review_tier"] == "close_identity_review"
    assert bool(gaps.loc[0, "automatic_match_performed"]) is False


def test_missing_zip_audit_keeps_only_genuinely_absent_values() -> None:
    audited = MODULE.audit_missing_zip_candidates(
        pd.DataFrame(
            {
                "profile_key": ["a"],
                "requested_location": ["Market_A"],
                "zip": [None],
                "normalized_zip": [None],
                "market_assignment_status": ["maps_missing_zip"],
            }
        )
    )
    assert audited["missing_zip_reason"].tolist() == ["source_zip_missing"]


def test_supplement_plan_deduplicates_reference_queries_and_batches() -> None:
    gaps = pd.DataFrame(
        {
            "reference_key": ["ref-1", "ref-2"],
            "market": ["Market_A", "Market_A"],
            "reference_title": ["Example Dental", "Example Dental"],
            "reference_address": ["1 Main St", "1 Main St"],
        }
    )
    regions = {
        "Market_A": {"location_code": 1001},
        "Market_B": {"location_code": 1002},
    }
    core, verification, combined = MODULE.build_maps_supplement_plan(
        ["Market_A", "Market_B", "Market_C"],
        gaps,
        {**regions, "Market_C": {"location_code": 1003}},
        core_keywords=["dentist", "dental clinic"],
        price_per_serp_usd=0.0006,
    )
    assert len(core) == 6
    assert len(verification) == 1
    assert verification.loc[0, "reference_location_count"] == 2
    assert not bool(verification.loc[0, "included_in_main_discovery_pipeline"])
    assert len(combined) == 6
    assert set(combined["market"]) == {"Market_A", "Market_B", "Market_C"}
    assert combined["included_in_main_discovery_pipeline"].all()
    assert combined["submission_batch"].tolist() == [1, 1, 1, 1, 1, 1]
