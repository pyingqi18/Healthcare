"""Tests for the non-decisional external profile evidence audit queue."""

from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.profile_eligibility_external_evidence import (
    prepare_external_evidence_audit,
)


def review_rows() -> pd.DataFrame:
    records = []
    values = [
        ("1", "block-shared", "a.example", "https://a.example/one", "111", ""),
        ("2", "block-shared", "a.example", "https://a.example/two", "222", ""),
        ("3", "block-web", "b.example", "https://b.example", "333", ""),
        ("4", "block-phone", "", "", "444", ""),
        ("5", "block-profile", "", "", "", ""),
        ("6", "block-decided", "c.example", "https://c.example", "555", "include_dental_provider"),
    ]
    for key, block, domain, website, phone, decision in values:
        records.append(
            {
                "decision_id": f"profile:Market:google:cid:{key}",
                "market": "Market",
                "profile_key": f"google:cid:{key}",
                "title": f"Clinic {key}",
                "address": f"{key} Main St",
                "observed_categories": "Medical clinic",
                "manual_decision": decision,
                "review_tier": "external_evidence_required",
                "source_phone": phone,
                "source_website_url": website,
                "normalized_source_domain": domain,
                "review_block_id": block,
                "direct_profile_evidence_url": f"https://www.google.com/maps?cid={key}",
            }
        )
    return pd.DataFrame.from_records(records)


def test_prepare_external_evidence_audit_builds_compact_routes() -> None:
    units, profiles, domains, summary = prepare_external_evidence_audit(review_rows())

    assert len(profiles) == 5
    assert len(units) == 4
    assert len(domains) == 2
    assert units.iloc[0]["evidence_route"] == "shared_domain_block"
    assert units.iloc[0]["profile_count"] == 2
    assert set(profiles["evidence_route"]) == {
        "shared_domain_block",
        "direct_website_singleton",
        "phone_and_profile_singleton",
        "profile_only_singleton",
    }
    assert "Clinic+4" in profiles.loc[
        profiles["profile_key"].eq("google:cid:4"), "profile_search_url"
    ].iloc[0]
    assert summary["already_decided_profiles"] == 1
    assert summary["external_evidence_profiles"] == 5
    assert summary["shared_domain_audit_units"] == 1
    assert summary["profiles_in_shared_domain_audit_units"] == 2
    assert summary["automatic_final_decisions_applied"] == 0


def test_prepare_external_evidence_audit_rejects_unsafe_shared_block() -> None:
    rows = review_rows()
    rows.loc[rows["profile_key"].eq("google:cid:2"), "normalized_source_domain"] = "other.example"

    with pytest.raises(ValueError, match="share one nonblank domain"):
        prepare_external_evidence_audit(rows)


def test_prepare_external_evidence_audit_rejects_duplicate_profile() -> None:
    rows = pd.concat([review_rows(), review_rows().iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate decision_id"):
        prepare_external_evidence_audit(rows)
