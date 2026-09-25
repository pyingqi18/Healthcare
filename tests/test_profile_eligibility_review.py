"""Tests for row-plus-group profile eligibility review application."""

from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.profile_eligibility_review import (
    apply_profile_eligibility_review,
    prepare_profile_eligibility_review,
)


def triage() -> pd.DataFrame:
    rows = []
    for key, group_id, suggestion in [
        ("google:cid:1", "g1", "include_dental_provider"),
        ("google:cid:2", "g1", "include_dental_provider"),
        ("google:cid:3", "g2", ""),
    ]:
        rows.append(
            {
                "decision_id": f"profile:Market:{key}",
                "market": "Market",
                "profile_key": key,
                "title": f"Clinic {key[-1]}",
                "address": "1 Main St",
                "observed_sources": "business_listings",
                "observed_categories": "Medical clinic",
                "observed_source_decisions": "needs_category_review",
                "profile_status_basis": "unreviewed_or_conflicting_category_evidence",
                "allowed_manual_decisions": (
                    "exclude_non_dentist_category|include_dental_provider"
                ),
                "manual_decision": "",
                "decision_evidence": "",
                "evidence_url": "",
                "reviewed_by": "",
                "reviewed_on": "",
                "category_group_id": group_id,
                "category_rule_pattern": "manual_review",
                "category_rule_reasons": "",
                "unknown_categories": "",
                "dental_title_signals": "dental" if suggestion else "",
                "nondental_title_signals": "",
                "category_nonprovider_signals": "",
                "suggested_manual_decision": suggestion,
                "review_tier": (
                    "focused_title_evidence"
                    if suggestion
                    else "external_evidence_required"
                ),
                "suggestion_basis": "review aid only",
                "automatic_final_decision_applied": False,
            }
        )
    return pd.DataFrame.from_records(rows)


def groups() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "category_group_id": "g1",
                "observed_categories": "Medical clinic",
                "observed_source_decisions": "needs_category_review",
                "category_rule_pattern": "manual_review",
                "review_tier": "focused_title_evidence",
                "suggested_manual_decision": "include_dental_provider",
                "suggestion_basis": "review aid only",
                "profile_count": 2,
                "markets": "Market",
                "sample_titles": "Clinic 1 || Clinic 2",
            },
            {
                "category_group_id": "g2",
                "observed_categories": "Medical clinic",
                "observed_source_decisions": "needs_category_review",
                "category_rule_pattern": "manual_review",
                "review_tier": "external_evidence_required",
                "suggested_manual_decision": "",
                "suggestion_basis": "review aid only",
                "profile_count": 1,
                "markets": "Market",
                "sample_titles": "Clinic 3",
            },
        ]
    )


def inventory() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "requested_location": "Market",
                "profile_key": f"google:cid:{key}",
                "phone": f"+1555000000{key}",
                "domain": "clinic.example" if key != 3 else "",
                "url": "https://clinic.example" if key != 3 else "",
                "votes_count": str(key * 10),
                "latitude": "40.0",
                "longitude": "-75.0",
            }
            for key in [1, 2, 3]
        ]
    )


def test_prepare_review_adds_urls_and_preserves_zero_automatic_decisions() -> None:
    rows, group_rows, summary = prepare_profile_eligibility_review(
        triage(), groups(), inventory()
    )

    assert rows.loc[0, "direct_profile_evidence_url"].endswith("cid=1")
    assert len(group_rows) == 2
    assert rows.loc[0, "source_website_url"] == "https://clinic.example"
    assert summary["profiles_with_existing_website"] == 2
    assert summary["profiles_with_phone"] == 3
    assert group_rows.set_index("category_group_id").loc[
        "g1", "profiles_with_dental_title_signal"
    ] == 2
    assert summary["profile_rows"] == 3
    assert summary["automatic_final_decisions_applied"] == 0
    assert summary["verified_profile_decisions_prefilled"] == 0


def test_prepare_review_prefills_exact_verified_decision_and_rejects_drift() -> None:
    verified = pd.DataFrame.from_records(
        [
            {
                "market": "Market",
                "profile_key": "google:cid:3",
                "title": "Clinic 3",
                "address": "1 Main St",
                "manual_decision": "include_dental_provider",
                "decision_evidence": "Official location page lists dentistry.",
                "evidence_url": "https://clinic.example/location-3",
                "reviewed_by": "official_site_audit",
                "reviewed_on": "2026-09-24",
            }
        ]
    )

    rows, _, summary = prepare_profile_eligibility_review(
        triage(), groups(), inventory(), verified
    )
    reviewed = rows.set_index("profile_key").loc["google:cid:3"]
    assert reviewed["manual_decision"] == "include_dental_provider"
    assert bool(reviewed["verified_decision_applied"])
    assert summary["verified_profile_decisions_prefilled"] == 1
    assert summary["automatic_final_decisions_applied"] == 0

    drifted = verified.copy()
    drifted.loc[0, "address"] = "Different address"
    with pytest.raises(ValueError, match="identity drift"):
        prepare_profile_eligibility_review(
            triage(), groups(), inventory(), drifted
        )


def test_prepare_review_splits_external_groups_by_repeated_domain() -> None:
    triage_rows = triage()
    triage_rows.loc[triage_rows["category_group_id"].eq("g1"), [
        "review_tier",
        "suggested_manual_decision",
        "dental_title_signals",
    ]] = ["external_evidence_required", "", ""]
    inventory_rows = inventory()
    inventory_rows.loc[
        inventory_rows["profile_key"].isin(["google:cid:1", "google:cid:2"]),
        ["domain", "url"],
    ] = ["shared.example", "https://shared.example"]

    rows, review_blocks, summary = prepare_profile_eligibility_review(
        triage_rows, groups(), inventory_rows
    )

    shared = review_blocks.loc[
        review_blocks["review_block_basis"].eq(
            "shared_domain_within_category_group"
        )
    ]
    assert len(shared) == 1
    assert int(shared.iloc[0]["profile_count"]) == 2
    assert rows.loc[rows["category_group_id"].eq("g1"), "review_block_id"].nunique() == 1
    assert summary["shared_domain_review_blocks"] == 1
    assert summary["profiles_in_shared_domain_review_blocks"] == 2


def test_prepare_review_does_not_group_unrelated_profiles_by_category() -> None:
    inventory_rows = inventory()
    inventory_rows.loc[
        inventory_rows["profile_key"].eq("google:cid:2"), ["domain", "url"]
    ] = ["other.example", "https://other.example"]

    rows, review_blocks, summary = prepare_profile_eligibility_review(
        triage(), groups(), inventory_rows
    )

    assert len(review_blocks) == 3
    assert rows.loc[rows["category_group_id"].eq("g1"), "review_block_id"].nunique() == 2
    assert review_blocks["review_block_basis"].eq("singleton_profile").all()
    assert summary["shared_domain_review_blocks"] == 0
    assert summary["singleton_review_blocks"] == 3


def test_apply_review_supports_group_decision_with_row_exception() -> None:
    rows, group_rows, _ = prepare_profile_eligibility_review(
        triage(), groups(), inventory()
    )
    group_rows.loc[group_rows["category_group_id"].eq("g1"), [
        "group_manual_decision",
        "reviewed_member_count",
        "group_decision_evidence",
        "reviewed_by",
        "reviewed_on",
    ]] = ["include_dental_provider", "2", "Reviewed both member profiles", "Reviewer", "2026-09-24"]
    group_rows.loc[group_rows["category_group_id"].eq("g2"), "group_manual_decision"] = "individual_review"
    rows.loc[rows["profile_key"].eq("google:cid:2"), [
        "manual_decision",
        "decision_evidence",
        "reviewed_by",
        "reviewed_on",
    ]] = ["exclude_non_dentist_category", "Confirmed non-provider", "Reviewer", "2026-09-24"]
    rows.loc[rows["profile_key"].eq("google:cid:3"), [
        "manual_decision",
        "decision_evidence",
        "reviewed_by",
        "reviewed_on",
    ]] = ["include_dental_provider", "Confirmed provider", "Reviewer", "2026-09-24"]

    blank = triage().loc[:, [
        "decision_id", "market", "profile_key", "title", "address",
        "observed_sources", "observed_categories", "observed_source_decisions",
        "profile_status_basis", "allowed_manual_decisions", "manual_decision",
        "decision_evidence", "evidence_url", "reviewed_by", "reviewed_on",
    ]]
    completed, audit, summary = apply_profile_eligibility_review(
        blank, rows, group_rows
    )

    decisions = completed.set_index("profile_key")["manual_decision"].to_dict()
    assert decisions == {
        "google:cid:1": "include_dental_provider",
        "google:cid:2": "exclude_non_dentist_category",
        "google:cid:3": "include_dental_provider",
    }
    assert audit["decision_source"].value_counts().to_dict() == {
        "individual_row": 2,
        "reviewed_group": 1,
    }
    assert summary["remaining_unresolved"] == 0


def test_apply_review_rejects_unreviewed_members_and_incomplete_profiles() -> None:
    rows, group_rows, _ = prepare_profile_eligibility_review(
        triage(), groups(), inventory()
    )
    group_rows.loc[group_rows["category_group_id"].eq("g1"), [
        "group_manual_decision",
        "reviewed_member_count",
        "group_decision_evidence",
        "reviewed_by",
        "reviewed_on",
    ]] = ["include_dental_provider", "1", "Only one checked", "Reviewer", "2026-09-24"]
    blank = triage().loc[:, [
        "decision_id", "market", "profile_key", "title", "address",
        "observed_sources", "observed_categories", "observed_source_decisions",
        "profile_status_basis", "allowed_manual_decisions", "manual_decision",
        "decision_evidence", "evidence_url", "reviewed_by", "reviewed_on",
    ]]
    with pytest.raises(ValueError, match="reviewed_member_count"):
        apply_profile_eligibility_review(blank, rows, group_rows)

    group_rows.loc[group_rows["category_group_id"].eq("g1"), [
        "reviewed_member_count"
    ]] = ["2"]
    with pytest.raises(ValueError, match="incomplete"):
        apply_profile_eligibility_review(blank, rows, group_rows)
