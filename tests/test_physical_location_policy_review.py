from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.physical_location_policy_review import (
    prepare_physical_location_policy_review,
)


def _triage() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "physical_location_group": "g1",
                "mapped_location": "Market",
                "profile_count": "2",
                "base_address_count": "1",
                "review_tier": "routine_shared_identity",
                "review_reason": "shared identity",
                "manual_decision": "pending_manual_review",
            },
            {
                "physical_location_group": "g2",
                "mapped_location": "Market",
                "profile_count": "2",
                "base_address_count": "2",
                "review_tier": "complex_review",
                "review_reason": "multiple base addresses",
                "manual_decision": "pending_manual_review",
            },
            {
                "physical_location_group": "g3",
                "mapped_location": "Market",
                "profile_count": "2",
                "base_address_count": "1",
                "review_tier": "focused_review",
                "review_reason": "mixed evidence",
                "manual_decision": "pending_manual_review",
            },
        ]
    )


def _profiles() -> pd.DataFrame:
    rows = []
    for group in ("g1", "g2", "g3"):
        for number in (1, 2):
            rows.append(
                {
                    "physical_location_group": group,
                    "clinic_key": f"{group}:{number}",
                    "title": f"Clinic {number}",
                    "address": f"{number} Main St",
                    "phone": "5550000000",
                    "domain": "example.test",
                    "profile_role": "organization",
                    "review_tier": (
                        "routine_shared_identity"
                        if group == "g1"
                        else "complex_review" if group == "g2" else "focused_review"
                    ),
                }
            )
    return pd.DataFrame(rows)


def _prepare(triage: pd.DataFrame | None = None, profiles: pd.DataFrame | None = None):
    return prepare_physical_location_policy_review(
        _triage() if triage is None else triage,
        _profiles() if profiles is None else profiles,
        expected_blocks=3,
        expected_profiles=6,
        expected_routine=1,
        expected_focused=1,
        expected_complex=1,
    )


def test_prepares_one_policy_table_and_narrows_manual_review() -> None:
    frames, summary = _prepare()

    decisions = frames["policy_decisions"].set_index("physical_location_group")
    assert decisions.loc["g1", "suggested_policy_decision"] == (
        "merge_current_block_as_one_physical_location"
    )
    assert decisions.loc["g2", "suggested_policy_decision"] == (
        "split_block_by_normalized_base_address"
    )
    assert set(frames["manual_review_queue"]["physical_location_group"]) == {"g3"}
    assert len(frames["manual_review_profiles"]) == 2
    assert summary["automatic_profile_or_location_merges"] == 0


def test_rejects_changed_tier_counts() -> None:
    triage = _triage()
    triage.loc[0, "review_tier"] = "focused_review"
    with pytest.raises(ValueError, match="Review-tier counts changed"):
        _prepare(triage=triage)


def test_rejects_incomplete_profile_coverage() -> None:
    with pytest.raises(ValueError, match="expected 6"):
        _prepare(profiles=_profiles().iloc[:-1].copy())


def test_keeps_every_manual_decision_field_blank() -> None:
    frames, _ = _prepare()
    decisions = frames["policy_decisions"]
    assert decisions[
        [
            "manual_policy_decision",
            "custom_partition_json",
            "decision_evidence",
            "reviewed_by",
            "reviewed_on",
        ]
    ].eq("").all(axis=None)
