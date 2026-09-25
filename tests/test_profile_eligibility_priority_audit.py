from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.profile_eligibility_priority_audit import (
    apply_priority_singleton_audit,
)


def _batch() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "priority_batch_sequence": ["1", "2"],
            "singleton_audit_sequence": ["3", "7"],
            "market": ["A", "B"],
            "profile_key": ["p1", "p2"],
            "title": ["Dental A", "Medical B"],
            "address": ["1 Main", "2 Main"],
        }
    )


def _decisions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "priority_batch_sequence": ["1", "2"],
            "profile_key": ["p1", "p2"],
            "manual_decision": [
                "include_dental_provider",
                "exclude_non_dentist_category",
            ],
            "decision_evidence": ["Exact dental page", "Exact non-dental page"],
            "evidence_url": ["https://a.example", "https://b.example"],
            "reviewed_by": ["reviewer", "reviewer"],
            "reviewed_on": ["2026-09-25", "2026-09-25"],
        }
    )


def _existing() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": ["Z"],
            "profile_key": ["p0"],
            "title": ["Old"],
            "address": ["0 Main"],
            "manual_decision": ["include_dental_provider"],
            "decision_evidence": ["old evidence"],
            "evidence_url": ["https://old.example"],
            "reviewed_by": ["reviewer"],
            "reviewed_on": ["2026-09-24"],
        }
    )


def test_apply_priority_singleton_audit_partitions_queue_and_appends() -> None:
    batch = _batch()
    singleton = pd.concat(
        [
            batch,
            pd.DataFrame(
                {
                    "priority_batch_sequence": [""],
                    "singleton_audit_sequence": ["8"],
                    "market": ["C"],
                    "profile_key": ["p3"],
                    "title": ["Pending"],
                    "address": ["3 Main"],
                }
            ),
        ],
        ignore_index=True,
    )
    additions, combined, remainder, summary = apply_priority_singleton_audit(
        batch, _decisions(), singleton, _existing()
    )
    assert len(additions) == 2
    assert set(combined["profile_key"]) == {"p0", "p1", "p2"}
    assert remainder["profile_key"].tolist() == ["p3"]
    assert summary["verified_decisions_after"] == 3
    assert summary["remaining_singleton_profiles"] == 1


def test_apply_priority_singleton_audit_rejects_incomplete_coverage() -> None:
    with pytest.raises(ValueError, match="coverage differs"):
        apply_priority_singleton_audit(
            _batch(), _decisions().iloc[:1], _batch(), _existing()
        )
