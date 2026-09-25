"""Tests for the local profile eligibility review app."""

from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.profile_eligibility_review_app import (
    build_profile_eligibility_review_app,
)


def rows() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "decision_id": f"profile:Market:{key}",
                "review_block_id": block,
                "market": "Market",
                "profile_key": f"google:cid:{key}",
                "title": f"Clinic {key}",
                "address": f"{key} Main St",
                "observed_categories": "Medical clinic",
                "review_tier": "external_evidence_required",
                "suggested_manual_decision": "",
                "source_phone": f"+1555000000{key}",
                "source_website_url": "https://shared.example",
                "direct_profile_evidence_url": f"https://www.google.com/maps?cid={key}",
                "existing_evidence_route": "website_then_google_profile",
                "manual_decision": "",
                "decision_evidence": "",
                "evidence_url": "",
                "reviewed_by": "",
                "reviewed_on": "",
            }
            for key, block in [(1, "b1"), (2, "b1"), (3, "b2")]
        ]
    )


def blocks() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "review_block_id": "b1",
                "review_block_basis": "shared_domain_within_category_group",
                "review_domain": "shared.example",
                "profile_count": "2",
                "review_tier": "external_evidence_required",
                "observed_categories": "Medical clinic",
                "suggested_manual_decision": "",
                "group_manual_decision": "",
                "reviewed_member_count": "",
                "group_decision_evidence": "",
                "reviewed_by": "",
                "reviewed_on": "",
            },
            {
                "review_block_id": "b2",
                "review_block_basis": "singleton_profile",
                "review_domain": "",
                "profile_count": "1",
                "review_tier": "external_evidence_required",
                "observed_categories": "Medical clinic",
                "suggested_manual_decision": "",
                "group_manual_decision": "",
                "reviewed_member_count": "",
                "group_decision_evidence": "",
                "reviewed_by": "",
                "reviewed_on": "",
            },
        ]
    )


def test_build_review_app_embeds_rows_blocks_and_export_logic() -> None:
    html, summary = build_profile_eligibility_review_app(rows(), blocks())

    assert summary["profile_rows"] == 3
    assert summary["review_blocks"] == 2
    assert summary["shared_domain_review_blocks"] == 1
    assert summary["singleton_review_blocks"] == 1
    assert summary["maximum_block_size"] == 2
    assert "Clinic 1" in html
    assert "profile_eligibility_review_groups_reviewed.csv" in html
    assert "profile_eligibility_review_rows_reviewed.csv" in html
    assert "members.every(rowComplete)" in html
    assert "localStorage" in html
    assert "reviewed_member_count" in html


def test_build_review_app_rejects_non_domain_multi_profile_block() -> None:
    invalid = blocks()
    invalid.loc[invalid["review_block_id"].eq("b1"), "review_block_basis"] = (
        "category_evidence_group"
    )

    with pytest.raises(ValueError, match="shared domain"):
        build_profile_eligibility_review_app(rows(), invalid)


def test_build_review_app_rejects_block_count_mismatch() -> None:
    invalid = blocks()
    invalid.loc[invalid["review_block_id"].eq("b1"), "profile_count"] = "3"

    with pytest.raises(ValueError, match="counts"):
        build_profile_eligibility_review_app(rows(), invalid)
