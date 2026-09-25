"""Tests for grouped cross-source profile eligibility review."""

from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.profile_eligibility_triage import (
    prepare_profile_eligibility_triage,
)


def decisions() -> pd.DataFrame:
    rows = [
        ("1", "Dental Lab", "Dental laboratory", "needs_category_review"),
        ("2", "Community Dental Center", "Medical clinic", "needs_category_review"),
        ("3", "Animal Wellness", "Veterinarian", "needs_category_review"),
        ("4", "Unclear Center", "Medical clinic", "needs_category_review"),
        ("5", "Mixed Dental", "Dentist|Medical clinic", "automatic_include|needs_category_review"),
    ]
    records = []
    for key, title, category, source_decision in rows:
        records.append(
            {
                "decision_id": f"profile:Market:{key}",
                "market": "Market",
                "profile_key": key,
                "title": title,
                "address": "1 Main St",
                "observed_sources": "maps_core",
                "observed_categories": category,
                "observed_source_decisions": source_decision,
                "profile_status_basis": "unreviewed_or_conflicting_category_evidence",
                "allowed_manual_decisions": "exclude_non_dentist_category|include_dental_provider",
                "manual_decision": "",
                "decision_evidence": "",
                "evidence_url": "",
                "reviewed_by": "",
                "reviewed_on": "",
            }
        )
    return pd.DataFrame.from_records(records)


def inventory() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "requested_location": ["Market"] * 5,
            "profile_key": ["1", "2", "3", "4", "5"],
            "preliminary_profile_status": ["pending_manual_review"] * 5,
        }
    )


def rules() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "category": ["Dental laboratory", "Medical clinic", "Dentist"],
            "category_decision": ["exclude", "manual_review", "include"],
            "reason": ["Auxiliary business", "Needs evidence", "Dental provider"],
        }
    )


def test_triage_separates_frozen_rules_title_signals_and_conflicts() -> None:
    triage, groups, unknown, summary = prepare_profile_eligibility_triage(
        decisions(), inventory(), rules()
    )
    indexed = triage.set_index("profile_key")

    assert indexed.loc["1", "review_tier"] == "routine_frozen_rule"
    assert indexed.loc["1", "suggested_manual_decision"] == "exclude_non_dentist_category"
    assert indexed.loc["2", "review_tier"] == "focused_title_evidence"
    assert indexed.loc["2", "suggested_manual_decision"] == "include_dental_provider"
    assert indexed.loc["3", "review_tier"] == "focused_category_evidence"
    assert indexed.loc["3", "suggested_manual_decision"] == "exclude_non_dentist_category"
    assert indexed.loc["4", "review_tier"] == "external_evidence_required"
    assert indexed.loc["5", "review_tier"] == "focused_category_conflict"
    assert not triage["automatic_final_decision_applied"].any()
    assert len(groups) == 5
    assert set(unknown["category"]) == {"Veterinarian"}
    assert summary["input_pending_profiles"] == 5
    assert summary["automatic_final_decisions_applied"] == 0


def test_triage_rejects_nonblank_or_incomplete_decision_template() -> None:
    nonblank = decisions()
    nonblank.loc[0, "manual_decision"] = "exclude_non_dentist_category"
    with pytest.raises(ValueError, match="unmodified blank"):
        prepare_profile_eligibility_triage(nonblank, inventory(), rules())

    incomplete = decisions().iloc[:-1].copy()
    with pytest.raises(ValueError, match="exactly cover"):
        prepare_profile_eligibility_triage(incomplete, inventory(), rules())
