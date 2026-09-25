from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.profile_eligibility_completion import (
    apply_remaining_completion,
    merge_remaining_decision_batch,
    prepare_remaining_completion,
)


def _remaining() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "singleton_audit_sequence": ["1", "2"],
            "market": ["A", "B"],
            "profile_key": ["google:cid:1", "google:cid:2"],
            "title": ["Clinic One", "Clinic Two"],
            "address": ["1 Main", "2 Main"],
            "observed_sources": ["maps_core", "business_listings"],
            "observed_categories": ["Medical clinic", "Pet groomer"],
            "source_phone": ["555-0001", ""],
            "source_domain": ["clinic.example", ""],
            "source_website_url": ["https://clinic.example", ""],
            "direct_profile_evidence_url": [
                "https://www.google.com/maps?cid=1",
                "https://www.google.com/maps?cid=2",
            ],
            "manual_decision": ["", ""],
            "decision_evidence": ["", ""],
            "evidence_url": ["", ""],
            "reviewed_by": ["", ""],
            "reviewed_on": ["", ""],
        }
    )


def _verified() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": ["Z"],
            "profile_key": ["google:cid:0"],
            "title": ["Old Dental"],
            "address": ["0 Main"],
            "manual_decision": ["include_dental_provider"],
            "decision_evidence": ["Exact official page"],
            "evidence_url": ["https://old.example"],
            "reviewed_by": ["reviewer"],
            "reviewed_on": ["2026-09-24"],
        }
    )


def test_prepare_and_apply_remaining_completion() -> None:
    prepared, groups, summary = prepare_remaining_completion(
        _remaining(), _verified()
    )
    assert len(prepared) == 2
    assert len(groups) == 2
    assert summary["final_profile_count_after_completion"] == 3
    assert prepared["exact_google_profile_url"].ne("").all()

    reviewed = prepared.copy()
    reviewed["manual_decision"] = [
        "include_dental_provider",
        "exclude_non_dentist_category",
    ]
    reviewed["decision_evidence"] = ["exact service page", "exact profile category"]
    reviewed["evidence_url"] = ["https://one.example", "https://two.example"]
    reviewed["reviewed_by"] = "reviewer"
    reviewed["reviewed_on"] = "2026-09-25"
    additions, combined, result = apply_remaining_completion(
        _remaining(), prepared, reviewed, _verified()
    )
    assert len(additions) == 2
    assert len(combined) == 3
    assert result["remaining_unresolved"] == 0


def test_apply_remaining_completion_rejects_blank_decision() -> None:
    prepared, _, _ = prepare_remaining_completion(_remaining(), _verified())
    with pytest.raises(ValueError, match="invalid values|incomplete"):
        apply_remaining_completion(_remaining(), prepared, prepared, _verified())


def test_merge_remaining_decision_batch_preserves_checkpoint_progress() -> None:
    prepared, _, _ = prepare_remaining_completion(_remaining(), _verified())
    checkpoint = prepared.copy()
    checkpoint.loc[0, "manual_decision"] = "include_dental_provider"
    checkpoint.loc[0, "decision_evidence"] = "official dental service page"
    checkpoint.loc[0, "evidence_url"] = "https://clinic.example/dental"
    checkpoint.loc[0, "reviewed_by"] = "reviewer"
    checkpoint.loc[0, "reviewed_on"] = "2026-09-25"

    merged, summary = merge_remaining_decision_batch(checkpoint, prepared)

    assert merged.loc[0, "manual_decision"] == "include_dental_provider"
    assert summary["decided_before"] == 1
    assert summary["new_decisions_added"] == 0
    assert summary["remaining_unresolved"] == 1


def test_merge_remaining_decision_batch_adds_new_complete_decision() -> None:
    prepared, _, _ = prepare_remaining_completion(_remaining(), _verified())
    batch = prepared.copy()
    batch.loc[1, "manual_decision"] = "exclude_non_dentist_category"
    batch.loc[1, "decision_evidence"] = "exact profile is a pet groomer"
    batch.loc[1, "evidence_url"] = "https://www.google.com/maps?cid=2"
    batch.loc[1, "reviewed_by"] = "reviewer"
    batch.loc[1, "reviewed_on"] = "2026-09-25"

    merged, summary = merge_remaining_decision_batch(prepared, batch)

    assert merged.loc[1, "manual_decision"] == "exclude_non_dentist_category"
    assert summary["new_decisions_added"] == 1
    assert summary["decided_after"] == 1


def test_merge_remaining_decision_batch_rejects_silent_conflict() -> None:
    prepared, _, _ = prepare_remaining_completion(_remaining(), _verified())
    checkpoint = prepared.copy()
    batch = prepared.copy()
    for frame, decision in [
        (checkpoint, "include_dental_provider"),
        (batch, "exclude_non_dentist_category"),
    ]:
        frame.loc[0, "manual_decision"] = decision
        frame.loc[0, "decision_evidence"] = decision
        frame.loc[0, "evidence_url"] = "https://evidence.example"
        frame.loc[0, "reviewed_by"] = "reviewer"
        frame.loc[0, "reviewed_on"] = "2026-09-25"

    with pytest.raises(ValueError, match="conflict"):
        merge_remaining_decision_batch(checkpoint, batch)


def test_merge_remaining_decision_batch_rejects_identity_change() -> None:
    prepared, _, _ = prepare_remaining_completion(_remaining(), _verified())
    batch = prepared.copy()
    batch.loc[0, "address"] = "changed address"

    with pytest.raises(ValueError, match="non-decision fields"):
        merge_remaining_decision_batch(prepared, batch)
