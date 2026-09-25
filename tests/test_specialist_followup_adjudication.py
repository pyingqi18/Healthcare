from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.specialist_followup_adjudication import (
    apply_specialist_followup_decisions,
    build_specialist_followup_decision_template,
)


def identity_queue() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": ["A", "A", "B"],
            "reference_key": ["r1", "r1", "r2"],
            "reference_title": ["Old One", "Old One", "Old Two"],
            "reference_address": ["1 Main", "1 Main", "2 Main"],
            "candidate_key": ["c1", "c2", "c3"],
            "candidate_title": ["One", "Other", "Two"],
            "candidate_category": ["Dentist"] * 3,
            "candidate_address": ["1 Main", "1 Main", "2 Main"],
            "distance_meters": [0.0, 2.0, 1.0],
            "title_similarity": [0.9, 0.2, 0.8],
            "best_candidate_from_38a": [True, False, True],
        }
    )


def profile_queue() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "review_type": [
                "specialist_only_manual_category",
                "specialist_missing_geography",
            ],
            "requested_location": ["A", "B"],
            "profile_key": ["p1", "p2"],
            "title": ["Dental Unit", "No Address Dentist"],
            "address": ["3 Main", pd.NA],
            "category": ["Medical clinic", "Dentist"],
            "google_category_evidence": ["Medical clinic", "Dentist"],
        }
    )


def profile_audit() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "requested_location": ["A", "B"],
            "profile_key": ["p1", "p2"],
            "category_rule_decision": ["manual_review", "include"],
        }
    )


def source_union() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": ["A", "A", "B", "B"],
            "reference_key": ["r1", "ra", "r2", "rb"],
            "current_reference_included": [True, True, True, True],
            "source_union_after_specialist": [False, True, False, True],
        }
    )


def completed_decisions(template: pd.DataFrame) -> pd.DataFrame:
    decisions = template.copy()
    decisions["decision_evidence"] = "Reviewed saved evidence"
    decisions["reviewed_by"] = "Reviewer"
    decisions["reviewed_on"] = "2026-09-20"
    decisions.loc[
        decisions["decision_id"].eq("identity:r1"),
        ["manual_decision", "selected_candidate_key"],
    ] = ["same_historical_location", "c1"]
    decisions.loc[
        decisions["decision_id"].eq("identity:r2"), "manual_decision"
    ] = "historical_location_closed"
    decisions.loc[
        decisions["decision_id"].eq("profile:p1"), "manual_decision"
    ] = "exclude_non_dentist_category"
    decisions.loc[
        decisions["decision_id"].eq("profile:p2"), "manual_decision"
    ] = "eligible_target_zip"
    return decisions


def test_template_combines_identity_category_and_geography_rows() -> None:
    template, summary = build_specialist_followup_decision_template(
        identity_queue(), profile_queue(), profile_audit()
    )
    assert len(template) == 4
    assert template["decision_id"].is_unique
    assert summary["identity_decision_rows"] == 2
    assert summary["category_decision_rows"] == 1
    assert summary["geography_decision_rows"] == 1
    r1 = template.set_index("decision_id").loc["identity:r1"]
    assert r1["candidate_pair_count"] == 2
    assert r1["suggested_candidate_key"] == "c1"


def test_apply_decisions_updates_matches_and_current_denominator() -> None:
    template, _ = build_specialist_followup_decision_template(
        identity_queue(), profile_queue(), profile_audit()
    )
    reviewed, confirmed, profiles, union, markets, summary = (
        apply_specialist_followup_decisions(
            template,
            completed_decisions(template),
            identity_queue(),
            source_union(),
            primary_market_minimum=0.9,
            reject_market_below=0.8,
        )
    )
    assert len(reviewed) == 4
    assert confirmed["subject_key"].tolist() == ["r1"]
    indexed = union.set_index("reference_key")
    assert indexed.loc["r1", "source_union_after_followup"]
    assert not indexed.loc["r2", "current_reference_included_after_followup"]
    assert profiles.set_index("subject_key").loc[
        "p2", "final_eligibility_review_status"
    ] == "include_dental_provider"
    assert markets.set_index("market").loc[
        "A", "source_union_recall_after_followup"
    ] == 1.0
    assert summary["adjudication_complete"]


def test_confirmed_identity_requires_a_candidate_from_its_pair_block() -> None:
    template, _ = build_specialist_followup_decision_template(
        identity_queue(), profile_queue(), profile_audit()
    )
    decisions = completed_decisions(template)
    decisions.loc[
        decisions["decision_id"].eq("identity:r1"), "selected_candidate_key"
    ] = "not-a-candidate"
    with pytest.raises(ValueError, match="listed candidate"):
        apply_specialist_followup_decisions(
            template,
            decisions,
            identity_queue(),
            source_union(),
            primary_market_minimum=0.9,
            reject_market_below=0.8,
        )


def test_decision_file_must_cover_every_template_row() -> None:
    template, _ = build_specialist_followup_decision_template(
        identity_queue(), profile_queue(), profile_audit()
    )
    decisions = completed_decisions(template).iloc[:-1].copy()
    with pytest.raises(ValueError, match="coverage differs"):
        apply_specialist_followup_decisions(
            template,
            decisions,
            identity_queue(),
            source_union(),
            primary_market_minimum=0.9,
            reject_market_below=0.8,
        )


def test_unresolved_summary_counts_unique_decision_rows_once() -> None:
    template, _ = build_specialist_followup_decision_template(
        identity_queue(), profile_queue(), profile_audit()
    )
    decisions = completed_decisions(template)
    decisions.loc[
        decisions["decision_type"].eq("historical_identity"), "manual_decision"
    ] = "unresolved"
    decisions.loc[
        decisions["decision_type"].eq("historical_identity"),
        "selected_candidate_key",
    ] = ""
    decisions.loc[
        decisions["decision_type"].eq("profile_category"), "manual_decision"
    ] = "unresolved"
    _, _, _, _, _, summary = apply_specialist_followup_decisions(
        template,
        decisions,
        identity_queue(),
        source_union(),
        primary_market_minimum=0.9,
        reject_market_below=0.8,
    )
    assert summary["remaining_unresolved_decisions"] == 3
    assert not summary["adjudication_complete"]
