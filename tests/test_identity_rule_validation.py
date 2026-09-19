"""Tests for broader historical identity-rule validation candidates."""

from __future__ import annotations

import pandas as pd

from medical_ratings.identity_rule_validation import (
    build_identity_rule_validation,
)


def queue() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market": "market",
                "reference_key": "exact",
                "reference_title": "Pearl Dental NYC",
                "reference_address": "233 Broadway Suite 1801",
                "nearest_candidate_distance_meters": 21.0,
                "review_tier": "close_identity_review",
                "review_priority": "high",
                "business_listings_best_candidate_key": "b1",
                "business_listings_best_candidate_title": "Pearl Dental NYC",
                "business_listings_best_candidate_address": "233 Broadway Ste 1801",
                "business_listings_best_distance_meters": 21.0,
                "business_listings_best_title_similarity": 1.0,
                "maps_standard_best_candidate_key": "m1",
                "maps_standard_best_candidate_title": "Other Dental",
                "maps_standard_best_candidate_address": "500 Broadway",
                "maps_standard_best_distance_meters": 400.0,
                "maps_standard_best_title_similarity": 0.3,
            },
            {
                "market": "market",
                "reference_key": "weak",
                "reference_title": "Old Dental",
                "reference_address": "1 Main Street",
                "nearest_candidate_distance_meters": 250.0,
                "review_tier": "nearby_identity_review",
                "review_priority": "standard",
                "business_listings_best_candidate_key": "b2",
                "business_listings_best_candidate_title": "Different Dental",
                "business_listings_best_candidate_address": "20 Main Street",
                "business_listings_best_distance_meters": 250.0,
                "business_listings_best_title_similarity": 0.4,
                "maps_standard_best_candidate_key": "m2",
                "maps_standard_best_candidate_title": "Another Dental",
                "maps_standard_best_candidate_address": "30 Main Street",
                "maps_standard_best_distance_meters": 300.0,
                "maps_standard_best_title_similarity": 0.3,
            },
        ]
    )


def test_exact_title_within_100m_enters_manual_validation() -> None:
    all_rows, candidates, summary = build_identity_rule_validation(queue())
    exact = all_rows.set_index("reference_key").loc["exact"]
    assert exact["business_listings_rule_exact_title_within_100m"]
    assert exact["validation_tier"] == "candidate_rule_manual_validation"
    assert list(candidates["reference_key"]) == ["exact"]
    assert summary["automatic_identity_matches"] == 0


def test_weak_nearby_candidate_remains_outside_rule() -> None:
    all_rows, _, _ = build_identity_rule_validation(queue())
    weak = all_rows.set_index("reference_key").loc["weak"]
    assert not weak["candidate_rule_match"]
    assert weak["validation_tier"] == "nearby_weak_identity"


def test_decision_columns_remain_blank() -> None:
    _, candidates, summary = build_identity_rule_validation(queue())
    assert candidates["proposed_decision"].eq("").all()
    assert candidates["decision_evidence"].eq("").all()
    assert "same_historical_location" in summary["allowed_proposed_decisions"]


def test_duplicate_reference_keys_are_rejected() -> None:
    duplicate = pd.concat([queue(), queue().iloc[[0]]], ignore_index=True)
    try:
        build_identity_rule_validation(duplicate)
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("Expected duplicate market-reference keys to fail")
