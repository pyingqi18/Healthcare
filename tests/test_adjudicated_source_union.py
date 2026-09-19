"""Tests for exact source-union recall changes after manual identity review."""

import pandas as pd

from medical_ratings.adjudicated_source_union import (
    apply_adjudication_to_source_union,
)


def source_union() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market": "A",
                "reference_key": "a:1",
                "business_listings_discovered": True,
                "maps_standard_discovered": False,
                "source_union_discovered": True,
                "source_discovery_status": "business_only",
            },
            {
                "market": "A",
                "reference_key": "a:2",
                "business_listings_discovered": False,
                "maps_standard_discovered": False,
                "source_union_discovered": False,
                "source_discovery_status": "not_discovered_by_either",
            },
            {
                "market": "B",
                "reference_key": "b:1",
                "business_listings_discovered": False,
                "maps_standard_discovered": False,
                "source_union_discovered": False,
                "source_discovery_status": "not_discovered_by_either",
            },
            {
                "market": "B",
                "reference_key": "b:2",
                "business_listings_discovered": False,
                "maps_standard_discovered": True,
                "source_union_discovered": True,
                "source_discovery_status": "maps_incremental",
            },
        ]
    )


def reviewed() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market": "A",
                "reference_key": "a:2",
                "proposed_decision": "same_historical_location",
                "confirmed_identity_match": True,
                "exclude_from_current_reference_denominator": False,
                "business_listings_candidate_rule_match": True,
                "maps_standard_candidate_rule_match": False,
            },
            {
                "market": "B",
                "reference_key": "b:1",
                "proposed_decision": "historical_reference_out_of_scope",
                "confirmed_identity_match": False,
                "exclude_from_current_reference_denominator": True,
                "business_listings_candidate_rule_match": True,
                "maps_standard_candidate_rule_match": False,
            },
        ]
    )


def run():
    return apply_adjudication_to_source_union(
        source_union(),
        reviewed(),
        expected_markets={"A", "B"},
        primary_market_minimum=0.9,
        reject_market_below=0.8,
    )


def test_recall_recalculation_adds_match_and_removes_exclusion() -> None:
    adjusted, by_market, summary = run()
    keyed = adjusted.set_index("reference_key")
    assert bool(keyed.loc["a:2", "source_union_discovered"])
    assert not bool(keyed.loc["b:1", "current_reference_included"])
    assert summary["original_fused_historical_target_zip_units"] == 4
    assert summary["adjusted_current_reference_units"] == 3
    assert summary["manually_confirmed_matches_added"] == 1
    assert summary["adjusted_source_union_discovered_units"] == 3
    assert summary["remaining_unmatched_current_references"] == 0
    assert by_market["fused_historical_target_zip_units"].sum() == 3


def test_recalculation_rejects_previously_discovered_review_row() -> None:
    bad = reviewed().copy()
    bad.loc[0, "reference_key"] = "a:1"
    try:
        apply_adjudication_to_source_union(
            source_union(),
            bad,
            expected_markets={"A", "B"},
            primary_market_minimum=0.9,
            reject_market_below=0.8,
        )
    except ValueError as error:
        assert "already discovered" in str(error)
    else:
        raise AssertionError("Expected an already discovered review row to fail")


def test_recalculation_rejects_match_and_exclusion_conflict() -> None:
    bad = reviewed().copy()
    bad.loc[0, "exclude_from_current_reference_denominator"] = True
    try:
        apply_adjudication_to_source_union(
            source_union(),
            bad,
            expected_markets={"A", "B"},
            primary_market_minimum=0.9,
            reject_market_below=0.8,
        )
    except ValueError as error:
        assert "both matched and denominator-excluded" in str(error)
    else:
        raise AssertionError("Expected conflicting manual decisions to fail")


def test_recalculation_keeps_api_and_merge_counts_zero() -> None:
    _, _, summary = run()
    assert summary["api_requests_submitted"] == 0
    assert summary["automatic_paid_follow_up"] is False
    assert summary["automatic_profile_or_location_merges"] == 0
