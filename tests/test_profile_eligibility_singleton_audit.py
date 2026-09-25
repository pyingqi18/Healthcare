"""Tests for prioritizing unresolved singleton profile evidence."""

from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.profile_eligibility_singleton_audit import (
    prepare_singleton_profile_audit,
)


def review_rows() -> pd.DataFrame:
    routes = [
        ("1", "https://example.org/dental-clinic", "111"),
        ("2", "https://example.org/locations/north-campus", "222"),
        ("3", "https://example.org/provider/jane-smith", "333"),
        ("4", "https://example.org/news", "444"),
        ("5", "https://example.org/", "555"),
        ("6", "", "666"),
        ("7", "", ""),
        ("8", "https://example.org/already-reviewed", "888"),
    ]
    records = []
    for key, website, phone in routes:
        title = "Jane Smith" if key == "3" else f"Clinic {key}"
        records.append(
            {
                "decision_id": f"profile:Market:google:cid:{key}",
                "market": "Market",
                "profile_key": f"google:cid:{key}",
                "title": title,
                "address": f"{key} Main St",
                "observed_categories": "Medical clinic",
                "manual_decision": (
                    "include_dental_provider" if key == "8" else ""
                ),
                "review_tier": "external_evidence_required",
                "suggested_manual_decision": "",
                "suggestion_basis": "",
                "source_phone": phone,
                "source_website_url": website,
                "normalized_source_domain": (
                    "example.org" if website else ""
                ),
                "direct_profile_evidence_url": (
                    f"https://www.google.com/maps?cid={key}"
                ),
                "review_block_id": f"block-{key}",
                "review_block_basis": "singleton_profile",
            }
        )
    return pd.DataFrame.from_records(records)


def test_prepare_singleton_audit_prioritizes_specific_pages_without_deciding() -> None:
    audit, priority_batch, summary = prepare_singleton_profile_audit(review_rows())

    routes = audit.set_index("profile_key")["singleton_evidence_route"]
    assert routes["google:cid:1"] == "direct_dental_service_page"
    assert routes["google:cid:2"] == "structured_official_page"
    assert routes["google:cid:3"] == "named_location_or_provider_page"
    assert routes["google:cid:4"] == "other_official_subpage"
    assert routes["google:cid:5"] == "official_homepage"
    assert routes["google:cid:6"] == "phone_and_google_profile"
    assert routes["google:cid:7"] == "google_profile_only"
    assert set(priority_batch["profile_key"]) == {
        "google:cid:1",
        "google:cid:2",
        "google:cid:3",
    }
    assert audit["audit_manual_decision"].eq("").all()
    assert summary["already_decided_profiles"] == 1
    assert summary["remaining_singleton_profiles"] == 7
    assert summary["specific_official_page_priority_batch"] == 3
    assert summary["automatic_final_decisions_applied"] == 0


def test_prepare_singleton_audit_rejects_unresolved_shared_block() -> None:
    rows = review_rows()
    rows.loc[rows["profile_key"].eq("google:cid:1"), "review_block_basis"] = (
        "shared_domain_within_category_group"
    )

    with pytest.raises(ValueError, match="non-singleton"):
        prepare_singleton_profile_audit(rows)


def test_prepare_singleton_audit_rejects_duplicate_profile() -> None:
    rows = pd.concat([review_rows(), review_rows().iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate decision_id"):
        prepare_singleton_profile_audit(rows)
