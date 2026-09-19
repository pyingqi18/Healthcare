from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.business_listings_manual_audit import (
    adjudicate_pilot_candidates,
    adjudicate_reference_locations,
    summarize_manual_audit,
)


def eligibility() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "clinic_key": "auto",
                "title": "Dentist",
                "market_assignment_status": "eligible_target_zip",
                "eligibility_review_status": "include_dental_provider",
            },
            {
                "clinic_key": "mixed",
                "title": "Mixed Clinic",
                "market_assignment_status": "eligible_target_zip",
                "eligibility_review_status": "manual_category_review",
            },
            {
                "clinic_key": "bad",
                "title": "Insurance",
                "market_assignment_status": "eligible_target_zip",
                "eligibility_review_status": "exclude_non_dentist_category",
            },
            {
                "clinic_key": "outside",
                "title": "Outside Dentist",
                "market_assignment_status": "outside_target_zip",
                "eligibility_review_status": "include_dental_provider",
            },
        ]
    )


def candidate_decisions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "clinic_key": "mixed",
                "competition_candidate_action": "include",
                "outcome_profile_action": "exclude",
                "manual_reason": "Dental service exists but rating is mixed.",
                "evidence_url": "https://example.com/mixed",
                "evidence_checked_at_utc": "2026-09-18T00:00:00Z",
            },
            {
                "clinic_key": "bad",
                "competition_candidate_action": "exclude",
                "outcome_profile_action": "exclude",
                "manual_reason": "Not dental.",
                "evidence_url": "https://example.com/bad",
                "evidence_checked_at_utc": "2026-09-18T00:00:00Z",
            },
        ]
    )


def reference_matches() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "reference_key": "found_auto",
                "market": "Syracuse_NY_M",
                "reference_title": "Dentist",
                "discovered": True,
            },
            {
                "reference_key": "found_mixed",
                "market": "Syracuse_NY_M",
                "reference_title": "Mixed Clinic",
                "discovered": True,
            },
            {
                "reference_key": "active_missing",
                "market": "Syracuse_NY_M",
                "reference_title": "Active Missing",
                "discovered": False,
            },
            {
                "reference_key": "closed",
                "market": "Syracuse_NY_M",
                "reference_title": "Closed Historical",
                "discovered": False,
            },
        ]
    )


def reference_decisions() -> pd.DataFrame:
    common = {
        "manual_reason": "Reviewed.",
        "evidence_url": "https://example.com/reference",
        "evidence_checked_at_utc": "2026-09-18T00:00:00Z",
    }
    return pd.DataFrame(
        [
            {
                "reference_key": "active_missing",
                "current_benchmark_action": "retain_current",
                "historical_panel_action": "retain_history",
                **common,
            },
            {
                "reference_key": "closed",
                "current_benchmark_action": "exclude_current",
                "historical_panel_action": "retain_history",
                **common,
            },
        ]
    )


def pairs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "reference_key": "found_auto",
                "candidate_key": "auto",
                "fixed_rule_match": True,
            },
            {
                "reference_key": "found_mixed",
                "candidate_key": "mixed",
                "fixed_rule_match": True,
            },
        ]
    )


def test_candidate_audit_separates_competition_and_outcome_actions() -> None:
    result = adjudicate_pilot_candidates(eligibility(), candidate_decisions()).set_index(
        "clinic_key"
    )
    assert result.loc["auto", "competition_candidate_included"]
    assert result.loc["auto", "outcome_profile_included"]
    assert result.loc["mixed", "competition_candidate_included"]
    assert not result.loc["mixed", "outcome_profile_included"]
    assert result.loc["outside", "competition_candidate_action"] == "out_of_scope"


def test_candidate_decisions_must_cover_every_exception_exactly() -> None:
    with pytest.raises(ValueError, match="exactly cover"):
        adjudicate_pilot_candidates(eligibility(), candidate_decisions().iloc[:1])


def test_reference_audit_separates_current_benchmark_and_history() -> None:
    candidates = adjudicate_pilot_candidates(eligibility(), candidate_decisions())
    result = adjudicate_reference_locations(
        reference_matches(), pairs(), candidates, reference_decisions()
    ).set_index("reference_key")
    assert result.loc["found_mixed", "discovered_with_competition_candidate"]
    assert not result.loc["found_mixed", "discovered_with_outcome_profile"]
    assert not result.loc["closed", "current_benchmark_included"]
    assert result.loc["closed", "historical_panel_included"]


def test_summary_uses_current_valid_reference_denominator() -> None:
    candidates = adjudicate_pilot_candidates(eligibility(), candidate_decisions())
    references = adjudicate_reference_locations(
        reference_matches(), pairs(), candidates, reference_decisions()
    )
    summary = summarize_manual_audit(candidates, references)
    assert summary["api_requests_submitted"] == 0
    assert summary["current_reference_benchmark_count"] == 3
    assert summary["historical_references_retained"] == 4
    assert summary["competition_discovery_recall"] == pytest.approx(2 / 3)
    assert summary["outcome_profile_discovery_recall"] == pytest.approx(1 / 3)
    assert summary["valid_current_references_not_discovered"] == ["active_missing"]
