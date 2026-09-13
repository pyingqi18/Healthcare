"""Tests for exact and complete manual candidate decisions."""

import pandas as pd

from medical_ratings.manual_candidate_review import (
    apply_manual_candidate_decisions,
)


def candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "clinic_key": "google:cid:1",
                "cid": "1",
                "title": "Confirmed dentist",
                "mapped_location": "Syracuse_NY_M",
                "eligibility_review_status": "include_dental_provider",
                "eligibility_review_reason": "Category rule",
            },
            {
                "clinic_key": "google:cid:2",
                "cid": "2",
                "title": "General clinic",
                "mapped_location": "Syracuse_NY_M",
                "eligibility_review_status": "manual_category_review",
                "eligibility_review_reason": "Review required",
            },
            {
                "clinic_key": "google:cid:3",
                "cid": "3",
                "title": "Service-area dentist",
                "mapped_location": None,
                "eligibility_review_status": "needs_geography",
                "eligibility_review_reason": "ZIP required",
            },
        ]
    )


def decisions() -> pd.DataFrame:
    common = {
        "evidence_url": "https://example.com/evidence",
        "evidence_checked_at_utc": "2026-09-10T00:00:00Z",
    }
    return pd.DataFrame(
        [
            {
                "clinic_key": "google:cid:2",
                "cid": "2",
                "reviewed_title": "General clinic",
                "manual_decision": "exclude_non_dentist_category",
                "manual_reason": "General medical provider",
                **common,
            },
            {
                "clinic_key": "google:cid:3",
                "cid": "3",
                "reviewed_title": "Service-area dentist",
                "manual_decision": "exclude_unverified_geography",
                "manual_reason": "No physical target-ZIP address",
                **common,
            },
        ]
    )


def test_manual_decisions_preserve_rows_and_resolve_all_candidates() -> None:
    reviewed = apply_manual_candidate_decisions(
        candidates(), decisions()
    ).set_index("clinic_key")

    assert len(reviewed) == 3
    assert int(reviewed["final_included"].sum()) == 1
    assert not reviewed["eligibility_review_status"].isin(
        {"manual_category_review", "needs_geography"}
    ).any()
    assert not bool(reviewed.loc["google:cid:1", "manual_review_applied"])
    assert reviewed.loc["google:cid:2", "eligibility_review_status"] == (
        "exclude_non_dentist_category"
    )
    assert reviewed.loc["google:cid:3", "eligibility_review_status"] == (
        "exclude_unverified_geography"
    )


def test_manual_decisions_reject_incomplete_unresolved_coverage() -> None:
    incomplete = decisions().iloc[[0]].copy()

    try:
        apply_manual_candidate_decisions(candidates(), incomplete)
    except ValueError as error:
        assert "coverage does not match" in str(error)
    else:
        raise AssertionError("Expected incomplete decision coverage to fail")


def test_manual_decisions_reject_candidate_identity_drift() -> None:
    changed = candidates()
    changed.loc[changed["cid"].eq("2"), "title"] = "Renamed clinic"

    try:
        apply_manual_candidate_decisions(changed, decisions())
    except ValueError as error:
        assert "title mismatch" in str(error)
    else:
        raise AssertionError("Expected changed candidate identity to fail")
