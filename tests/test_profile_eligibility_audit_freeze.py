"""Tests for shared-domain profile decisions and evidence freezing."""

import pandas as pd
import pytest

from medical_ratings.profile_eligibility_audit_freeze import (
    merge_verified_decisions,
    validate_shared_domain_decisions,
)


def profiles() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "decision_id": f"profile:{key}",
                "market": "Market_A",
                "profile_key": key,
                "title": title,
                "address": address,
                "manual_decision": "",
                "decision_evidence": "",
                "evidence_url": "",
                "reviewed_by": "",
                "reviewed_on": "",
                "audit_unit_profile_count": "2",
                "review_block_id": "block:shared",
                "normalized_source_domain": "example.org",
            }
            for key, title, address in [
                ("google:cid:1", "Dental site", "1 Main St"),
                ("google:cid:2", "Medical site", "2 Main St"),
            ]
        ]
    )


def decisions() -> pd.DataFrame:
    frame = profiles()[["market", "profile_key", "title", "address"]].copy()
    frame["manual_decision"] = [
        "include_dental_provider",
        "exclude_non_dentist_category",
    ]
    frame["decision_evidence"] = ["Exact dental service", "Exact medical-only service"]
    frame["evidence_url"] = ["https://example.org/1", "https://example.org/2"]
    frame["reviewed_by"] = "official_site_audit"
    frame["reviewed_on"] = "2026-09-24"
    return frame


def test_validate_shared_domain_decisions_preserves_profile_level_difference() -> None:
    audited, summary = validate_shared_domain_decisions(profiles(), decisions())
    assert len(audited) == 2
    assert summary["shared_domain_review_units"] == 1
    assert summary["include_dental_provider"] == 1
    assert summary["exclude_non_dentist_category"] == 1
    assert summary["automatic_profile_or_location_merges"] == 0


def test_validate_shared_domain_decisions_rejects_identity_drift() -> None:
    changed = decisions()
    changed.loc[0, "address"] = "different address"
    with pytest.raises(ValueError, match="identity"):
        validate_shared_domain_decisions(profiles(), changed)


def test_merge_verified_decisions_rejects_duplicate_profile() -> None:
    with pytest.raises(ValueError, match="already contain"):
        merge_verified_decisions(decisions().iloc[[0]], decisions().iloc[[0]])
