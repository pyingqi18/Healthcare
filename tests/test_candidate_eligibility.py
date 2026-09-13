"""Tests for auditable candidate eligibility review statuses."""

import pandas as pd

from medical_ratings.candidate_eligibility import (
    apply_candidate_eligibility_review,
)


def test_candidate_review_preserves_rows_and_assigns_statuses() -> None:
    candidates = pd.DataFrame(
        [
            {
                "clinic_key": "google:cid:1",
                "category": "Dentist",
                "market_assignment_status": "eligible_target_zip",
            },
            {
                "clinic_key": "google:cid:2",
                "category": "Pharmacy",
                "market_assignment_status": "eligible_target_zip",
            },
            {
                "clinic_key": "google:cid:3",
                "category": "Medical clinic",
                "market_assignment_status": "eligible_target_zip",
            },
            {
                "clinic_key": "google:cid:4",
                "category": None,
                "market_assignment_status": "local_finder_only_unlocated",
            },
            {
                "clinic_key": "google:cid:5",
                "category": "Dentist",
                "market_assignment_status": "outside_target_zip",
            },
        ]
    )
    rules = pd.DataFrame(
        [
            {
                "category": "Dentist",
                "category_decision": "include",
                "reason": "Dental provider",
            },
            {
                "category": "Pharmacy",
                "category_decision": "exclude",
                "reason": "Non-dental business",
            },
            {
                "category": "Medical clinic",
                "category_decision": "manual_review",
                "reason": "Ambiguous category",
            },
        ]
    )

    reviewed = apply_candidate_eligibility_review(candidates, rules).set_index(
        "clinic_key"
    )

    assert len(reviewed) == 5
    assert reviewed.loc["google:cid:1", "eligibility_review_status"] == (
        "include_dental_provider"
    )
    assert reviewed.loc["google:cid:2", "eligibility_review_status"] == (
        "exclude_non_dentist_category"
    )
    assert reviewed.loc["google:cid:3", "eligibility_review_status"] == (
        "manual_category_review"
    )
    assert reviewed.loc["google:cid:4", "eligibility_review_status"] == (
        "needs_geography"
    )
    assert reviewed.loc["google:cid:5", "eligibility_review_status"] == (
        "exclude_outside_target_zip"
    )


def test_candidate_review_rejects_duplicate_rule_categories() -> None:
    candidates = pd.DataFrame(
        [
            {
                "clinic_key": "google:cid:1",
                "category": "Dentist",
                "market_assignment_status": "eligible_target_zip",
            }
        ]
    )
    rules = pd.DataFrame(
        [
            {
                "category": "Dentist",
                "category_decision": "include",
                "reason": "First rule",
            },
            {
                "category": " dentist ",
                "category_decision": "exclude",
                "reason": "Conflicting rule",
            },
        ]
    )

    try:
        apply_candidate_eligibility_review(candidates, rules)
    except ValueError as error:
        assert "duplicate categories" in str(error)
    else:
        raise AssertionError("Expected duplicate category rules to fail")
