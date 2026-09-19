"""Tests for offline triage of references missed by both sources."""

from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.unmatched_reference_audit import (
    build_unmatched_reference_review,
    summarize_unmatched_reference_review,
)


def inputs() -> tuple[pd.DataFrame, ...]:
    union = pd.DataFrame(
        {
            "market": ["small", "small", "large"],
            "reference_key": ["r1", "r2", "r3"],
            "source_discovery_status": [
                "not_discovered_by_either",
                "not_discovered_by_either",
                "business_only",
            ],
        }
    )
    universe = pd.DataFrame(
        [
            {"search_location": "small", "clinic_key": "r1", "title": "A Dental", "address": "1 Main", "zip": "10001", "latitude": 40.0, "longitude": -74.0, "phone": None, "domain": None, "reference_geography_status": "eligible_target_zip"},
            {"search_location": "small", "clinic_key": "r2", "title": "B Dental", "address": None, "zip": "10001", "latitude": None, "longitude": None, "phone": None, "domain": None, "reference_geography_status": "eligible_target_zip"},
            {"search_location": "large", "clinic_key": "r3", "title": "C Dental", "address": "3 Main", "zip": "20001", "latitude": 38.9, "longitude": -77.0, "phone": None, "domain": None, "reference_geography_status": "eligible_target_zip"},
        ]
    )
    business = pd.DataFrame(
        {
            "market": ["small", "small", "large"],
            "reference_key": ["r1", "r2", "r3"],
            "discovered": [False, False, True],
            "coordinate_only_review_candidate_count": [1, 0, 0],
            "best_candidate_key": ["b1", None, "b3"],
            "best_distance_meters": [8.0, None, 0.0],
        }
    )
    maps = pd.DataFrame(
        {
            "market": ["small", "small", "large"],
            "reference_key": ["r1", "r2", "r3"],
            "discovered": [False, False, False],
            "coordinate_only_review_candidate_count": [0, 0, 0],
            "best_candidate_key": ["m1", None, None],
            "best_distance_meters": [300.0, None, None],
        }
    )
    market = pd.DataFrame(
        {
            "market": ["small", "large"],
            "remaining_unmatched_units": [2, 0],
            "benchmark_decision": ["discovery_redesign_required", "meets_primary_market_gate"],
        }
    )
    return union, universe, business, maps, market


def test_queue_prioritizes_close_identity_and_missing_reference_evidence() -> None:
    review = build_unmatched_reference_review(*inputs())
    tier = review.set_index("reference_key")["review_tier"]
    assert tier["r1"] == "close_identity_review"
    assert tier["r2"] == "insufficient_reference_identity"
    assert set(review["review_priority"]) == {"high"}
    assert review["manual_decision"].eq("").all()


def test_queue_excludes_references_found_by_either_source() -> None:
    review = build_unmatched_reference_review(*inputs())
    assert set(review["reference_key"]) == {"r1", "r2"}


def test_queue_rejects_market_count_drift() -> None:
    values = list(inputs())
    values[-1] = values[-1].copy()
    values[-1].loc[values[-1]["market"].eq("small"), "remaining_unmatched_units"] = 3
    with pytest.raises(ValueError, match="count differs"):
        build_unmatched_reference_review(*values)


def test_summary_keeps_all_decisions_manual() -> None:
    review = build_unmatched_reference_review(*inputs())
    by_market, summary = summarize_unmatched_reference_review(review)
    assert summary["unmatched_reference_units"] == 2
    assert summary["automatic_current_status_decisions"] == 0
    assert summary["automatic_paid_follow_up"] is False
    assert by_market["unmatched_reference_units"].sum() == 2
