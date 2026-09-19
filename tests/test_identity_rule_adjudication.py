"""Tests for complete, identity-stable adjudication of candidate matches."""

import pandas as pd

from medical_ratings.identity_rule_adjudication import (
    apply_identity_rule_adjudication,
)


def candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market": "Atlanta_GA_L",
                "reference_key": "reference:1",
                "reference_title": "Same Dental",
                "candidate_rule_match": True,
            },
            {
                "market": "Modesto_CA_M",
                "reference_key": "reference:2",
                "reference_title": "General Pediatrics",
                "candidate_rule_match": True,
            },
        ]
    )


def decisions() -> pd.DataFrame:
    common = {
        "evidence_checked_at_utc": "2026-09-19T00:00:00Z",
        "reviewed_by": "evidence audit",
    }
    return pd.DataFrame(
        [
            {
                "reference_key": "reference:1",
                "reviewed_reference_title": "Same Dental",
                "proposed_decision": "same_historical_location",
                "decision_evidence": "Same title and address.",
                "evidence_url": "https://example.com/1",
                **common,
            },
            {
                "reference_key": "reference:2",
                "reviewed_reference_title": "General Pediatrics",
                "proposed_decision": "historical_reference_out_of_scope",
                "decision_evidence": "Medical pediatrics rather than dentistry.",
                "evidence_url": "https://example.com/2",
                **common,
            },
        ]
    )


def test_adjudication_reports_matches_exclusions_and_precision() -> None:
    reviewed, confirmed, exclusions, summary = apply_identity_rule_adjudication(
        candidates(), decisions()
    )
    assert len(reviewed) == 2
    assert len(confirmed) == 1
    assert len(exclusions) == 1
    assert summary["candidate_rule_positive_predictive_value"] == 0.5
    assert not summary["candidate_rule_generalization_approved"]


def test_adjudication_requires_complete_decision_coverage() -> None:
    try:
        apply_identity_rule_adjudication(candidates(), decisions().iloc[[0]])
    except ValueError as error:
        assert "coverage does not match" in str(error)
    else:
        raise AssertionError("Expected incomplete decisions to fail")


def test_adjudication_rejects_reference_title_drift() -> None:
    changed = decisions()
    changed.loc[0, "reviewed_reference_title"] = "Changed Dental"
    try:
        apply_identity_rule_adjudication(candidates(), changed)
    except ValueError as error:
        assert "title changed" in str(error)
    else:
        raise AssertionError("Expected title drift to fail")


def test_adjudication_never_merges_profiles_automatically() -> None:
    _, _, _, summary = apply_identity_rule_adjudication(
        candidates(), decisions()
    )
    assert summary["automatic_profile_or_location_merges"] == 0
