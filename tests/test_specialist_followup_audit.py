from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.specialist_followup_audit import (
    build_market_gap_diagnostic,
    build_specialist_identity_review_queue,
    build_specialist_profile_review_queue,
)


def remaining() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": ["A", "A", "B"],
            "reference_key": ["a1", "a2", "b1"],
            "maps_specialist_best_candidate_key": ["c1", "c2", "c3"],
            "maps_specialist_best_matching_evidence": [
                "coordinate_only_within_10m_review",
                "nearest_candidate_only",
                "nearest_candidate_only",
            ],
        }
    )


def match_pairs() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": ["A", "A", "A"],
            "reference_key": ["a1", "a1", "a2"],
            "reference_title": ["Old A", "Old A", "Old B"],
            "reference_address": ["1 Main", "1 Main", "2 Main"],
            "candidate_key": ["c1-alt", "c1", "c2"],
            "candidate_cid": ["11", "12", "13"],
            "candidate_title": ["Other", "Old A", "Far"],
            "candidate_category": ["Dentist"] * 3,
            "candidate_address": ["1 Main"] * 3,
            "eligibility_review_status": ["include_dental_provider"] * 3,
            "same_normalized_address": [False, False, False],
            "same_phone": [False, False, False],
            "distance_meters": [5.0, 1.0, 200.0],
            "title_similarity": [0.2, 1.0, 0.1],
            "matching_evidence": [
                "coordinate_only_within_10m_review",
                "coordinate_only_within_10m_review",
                "nearest_candidate_only",
            ],
            "fixed_rule_match": [False, False, False],
        }
    )


def profile_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "requested_location": ["A", "A", "B"],
            "profile_key": ["new-manual", "missing-zip", "seen-manual"],
            "cid": ["1", "2", "3"],
            "place_id": ["p1", "p2", "p3"],
            "title": ["Manual", "No ZIP", "Seen"],
            "category": ["Clinic"] * 3,
            "address": ["1 Main", "", "3 Main"],
            "zip": ["10001", pd.NA, "20001"],
            "market_assignment_status": [
                "eligible_target_zip",
                "maps_missing_zip",
                "eligible_target_zip",
            ],
            "eligibility_review_status": [
                "manual_category_review",
                "needs_geography",
                "manual_category_review",
            ],
            "specialist_exact_profile_status": [
                "specialist_only_exact_profile",
                "not_compared_missing_geography",
                "seen_in_core_maps_only",
            ],
        }
    )


def market_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": ["A", "B"],
            "current_reference_units": [10, 10],
            "source_union_after_specialist_units": [7, 8],
            "source_union_after_specialist_recall": [0.7, 0.8],
            "remaining_unmatched_reference_units": [3, 2],
            "benchmark_decision_after_specialist": [
                "discovery_redesign_required",
                "targeted_gap_audit_required",
            ],
        }
    )


def test_identity_queue_keeps_all_pairs_for_pending_reference() -> None:
    queue = build_specialist_identity_review_queue(remaining(), match_pairs())
    assert queue["reference_key"].tolist() == ["a1", "a1"]
    assert queue["candidate_rank_within_reference"].tolist() == [1, 2]
    assert queue["best_candidate_from_38a"].tolist() == [True, False]
    assert queue["manual_pair_decision"].eq("").all()


def test_identity_queue_rejects_fixed_rule_match() -> None:
    pairs = match_pairs()
    pairs.loc[0, "fixed_rule_match"] = True
    with pytest.raises(ValueError, match="fixed-rule"):
        build_specialist_identity_review_queue(remaining(), pairs)


def test_profile_queue_keeps_only_new_manual_and_missing_zip() -> None:
    profiles = profile_rows()
    queue = build_specialist_profile_review_queue(profiles, profiles)
    assert set(queue["profile_key"]) == {"new-manual", "missing-zip"}
    assert set(queue["review_type"]) == {
        "specialist_only_manual_category",
        "specialist_missing_geography",
    }
    assert queue["manual_decision"].eq("").all()


def test_gap_diagnostic_does_not_let_profile_reviews_raise_recall() -> None:
    identity = build_specialist_identity_review_queue(remaining(), match_pairs())
    profiles = build_specialist_profile_review_queue(profile_rows(), profile_rows())
    diagnostic, summary = build_market_gap_diagnostic(
        market_rows(),
        remaining(),
        identity,
        profiles,
        expected_markets={"A", "B"},
        primary_market_minimum=0.9,
        reject_market_below=0.8,
    )
    indexed = diagnostic.set_index("market")
    assert indexed.loc["A", "maximum_recall_if_all_pending_identity_confirmed"] == 0.8
    assert indexed.loc["A", "recommended_next_action"] == (
        "complete_identity_review_before_redesign_decision"
    )
    assert indexed.loc["B", "recommended_next_action"] == (
        "targeted_current_status_audit"
    )
    assert summary["uniform_discovery_redesign_triggered"] is False


def test_gap_diagnostic_requires_uniform_redesign_when_identity_cannot_reach_gate() -> None:
    diagnostic, summary = build_market_gap_diagnostic(
        market_rows(),
        remaining(),
        pd.DataFrame(columns=["market", "reference_key"]),
        pd.DataFrame(columns=["requested_location", "review_type"]),
        expected_markets={"A", "B"},
        primary_market_minimum=0.9,
        reject_market_below=0.8,
    )
    indexed = diagnostic.set_index("market")
    assert indexed.loc["A", "recommended_next_action"] == (
        "uniform_discovery_redesign_required_after_status_audit"
    )
    assert summary["markets_requiring_uniform_discovery_redesign"] == ["A"]
