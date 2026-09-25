"""Validate and apply exact-profile decisions from the priority singleton audit."""

from __future__ import annotations

from typing import Any

import pandas as pd

from medical_ratings.profile_eligibility_audit_freeze import (
    ALLOWED_DECISIONS,
    DECISION_COLUMN_ORDER,
    merge_verified_decisions,
)


PRIORITY_DECISION_COLUMNS = {
    "priority_batch_sequence",
    "profile_key",
    "manual_decision",
    "decision_evidence",
    "evidence_url",
    "reviewed_by",
    "reviewed_on",
}
IDENTITY_COLUMNS = ["market", "profile_key", "title", "address"]


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.copy()
    for column in cleaned.columns:
        cleaned[column] = cleaned[column].fillna("").astype(str).str.strip()
    return cleaned


def _require(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def apply_priority_singleton_audit(
    priority_batch: pd.DataFrame,
    decisions: pd.DataFrame,
    singleton_audit: pd.DataFrame,
    verified_decisions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Apply a complete priority batch and return additions, combined freeze, remainder."""

    _require(
        priority_batch,
        set(IDENTITY_COLUMNS) | {"priority_batch_sequence"},
        "priority batch",
    )
    _require(decisions, PRIORITY_DECISION_COLUMNS, "priority decisions")
    _require(
        singleton_audit,
        set(IDENTITY_COLUMNS) | {"singleton_audit_sequence"},
        "singleton audit",
    )
    batch = _clean(priority_batch)
    reviewed = _clean(decisions)
    pending = _clean(singleton_audit)

    for label, frame in (("priority batch", batch), ("priority decisions", reviewed)):
        if frame["profile_key"].duplicated().any():
            raise ValueError(f"{label} contains duplicate profile keys")
    if set(batch["profile_key"]) != set(reviewed["profile_key"]):
        missing = sorted(set(batch["profile_key"]) - set(reviewed["profile_key"]))
        extra = sorted(set(reviewed["profile_key"]) - set(batch["profile_key"]))
        raise ValueError(
            "Priority decision coverage differs from the frozen batch; "
            f"missing={missing}, extra={extra}"
        )

    expected_sequence = batch.set_index("profile_key")["priority_batch_sequence"]
    observed_sequence = reviewed.set_index("profile_key")["priority_batch_sequence"]
    observed_sequence = observed_sequence.reindex(expected_sequence.index)
    if not expected_sequence.equals(observed_sequence):
        raise ValueError("Priority decision sequence differs from the frozen batch")
    invalid = sorted(set(reviewed["manual_decision"]) - ALLOWED_DECISIONS)
    if invalid:
        raise ValueError(f"Priority decisions contain invalid values: {invalid}")
    required_evidence = [
        "decision_evidence",
        "evidence_url",
        "reviewed_by",
        "reviewed_on",
    ]
    blank = reviewed[required_evidence].eq("").any(axis=1)
    if blank.any():
        keys = reviewed.loc[blank, "profile_key"].tolist()
        raise ValueError(f"Priority decisions have incomplete evidence: {keys}")

    additions = batch[IDENTITY_COLUMNS].merge(
        reviewed[
            [
                "profile_key",
                "manual_decision",
                "decision_evidence",
                "evidence_url",
                "reviewed_by",
                "reviewed_on",
            ]
        ],
        on="profile_key",
        how="left",
        validate="one_to_one",
    )
    additions = additions[DECISION_COLUMN_ORDER].sort_values(
        ["market", "title", "profile_key"], kind="stable", ignore_index=True
    )
    combined = merge_verified_decisions(verified_decisions, additions)

    reviewed_keys = set(additions["profile_key"])
    remainder = pending.loc[~pending["profile_key"].isin(reviewed_keys)].copy()
    remainder = remainder.sort_values(
        ["singleton_audit_sequence"], kind="stable", ignore_index=True
    )
    if len(remainder) + len(additions) != len(pending):
        raise ValueError("Priority decisions do not partition the singleton audit")

    summary = {
        "analysis_status": "specific_official_page_priority_audit_applied",
        "api_requests_submitted": 0,
        "priority_profiles_reviewed": int(len(additions)),
        "include_dental_provider": int(
            additions["manual_decision"].eq("include_dental_provider").sum()
        ),
        "exclude_non_dentist_category": int(
            additions["manual_decision"].eq("exclude_non_dentist_category").sum()
        ),
        "verified_decisions_before": int(len(verified_decisions)),
        "verified_decisions_after": int(len(combined)),
        "remaining_singleton_profiles": int(len(remainder)),
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
        "next_required_action": (
            "Review the remaining singleton file in one consolidated pass, then run "
            "physical-location resolution and rebuild the final panel."
        ),
    }
    return additions, combined, remainder, summary
