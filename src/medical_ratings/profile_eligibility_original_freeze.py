"""Validate the untouched profile-eligibility review baseline and its lineage."""

from __future__ import annotations

from typing import Any

import pandas as pd


IDENTITY_COLUMNS = ["market", "profile_key", "title", "address"]


def _require(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        result[column] = result[column].fillna("").astype(str).str.strip()
    return result


def _validate_blank_decisions(frame: pd.DataFrame, label: str, expected: int) -> None:
    _require(frame, set(IDENTITY_COLUMNS) | {"manual_decision"}, label)
    if len(frame) != expected or frame["profile_key"].nunique() != expected:
        raise ValueError(f"{label} must contain {expected} unique profile keys")
    if frame["manual_decision"].ne("").any():
        raise ValueError(f"{label} is not an untouched blank-decision file")


def validate_original_review_lineage(
    initial_pending: pd.DataFrame,
    corrected_pending: pd.DataFrame,
    canonical_rows: pd.DataFrame,
    canonical_groups: pd.DataFrame,
    triage: pd.DataFrame,
    inventory: pd.DataFrame,
) -> dict[str, Any]:
    """Prove the 583 to 570 to 450 lineage and the final 410-block structure."""

    initial = _clean(initial_pending)
    corrected = _clean(corrected_pending)
    rows = _clean(canonical_rows)
    groups = _clean(canonical_groups)
    triaged = _clean(triage)
    inventory_clean = _clean(inventory)
    _validate_blank_decisions(initial, "initial 46a pending decisions", 583)
    _validate_blank_decisions(corrected, "corrected 46a pending decisions", 570)
    _validate_blank_decisions(rows, "canonical manual-review rows", 450)
    _require(
        groups,
        {"review_block_id", "profile_count", "group_manual_decision"},
        "canonical review groups",
    )
    if len(groups) != 410 or groups["review_block_id"].nunique() != 410:
        raise ValueError("Canonical review groups must contain 410 unique blocks")
    if groups["group_manual_decision"].ne("").any():
        raise ValueError("Canonical review groups contain a decision and are not original")
    if pd.to_numeric(groups["profile_count"], errors="raise").sum() != 450:
        raise ValueError("Canonical review block membership does not sum to 450")
    _require(triaged, set(IDENTITY_COLUMNS), "profile eligibility triage")
    _require(
        inventory_clean,
        {"requested_location", "profile_key"},
        "source profile inventory",
    )

    initial_keys = set(initial["profile_key"])
    corrected_keys = set(corrected["profile_key"])
    canonical_keys = set(rows["profile_key"])
    if not corrected_keys < initial_keys:
        raise ValueError("The corrected 570-profile queue is not a strict initial subset")
    if not canonical_keys < corrected_keys:
        raise ValueError("The canonical 450-profile cohort is not a strict corrected subset")
    if len(initial_keys - corrected_keys) != 13:
        raise ValueError("Expected 13 profiles resolved by prior-decision reuse")
    if len(corrected_keys - canonical_keys) != 120:
        raise ValueError("Expected 120 profiles resolved by frozen category exclusions")
    triage_identity = triaged[IDENTITY_COLUMNS].sort_values(
        "profile_key", ignore_index=True
    )
    row_identity = rows[IDENTITY_COLUMNS].sort_values("profile_key", ignore_index=True)
    if not row_identity.equals(triage_identity):
        raise ValueError("Canonical review rows differ from the frozen triage identities")
    inventory_pairs = set(
        zip(inventory_clean["requested_location"], inventory_clean["profile_key"])
    )
    row_pairs = set(zip(rows["market"], rows["profile_key"]))
    if not row_pairs <= inventory_pairs:
        raise ValueError("Canonical review profiles are missing from the source inventory")

    return {
        "analysis_status": "original_profile_eligibility_review_baseline_frozen",
        "api_requests_submitted": 0,
        "initial_46a_blank_pending_profiles": 583,
        "prior_decision_reuse_resolved_profiles": 13,
        "corrected_46a_blank_pending_profiles": 570,
        "frozen_category_exclusions_resolved_profiles": 120,
        "canonical_manual_review_profiles": 450,
        "canonical_manual_review_profiles_with_decision": 0,
        "canonical_review_blocks": 410,
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
        "canonical_review_file": "02_canonical_manual_review_rows_450_blank.csv",
        "interpretation": (
            "The 450-row file is the untouched manual-review baseline. Later v8 and "
            "v9 files are progress checkpoints with 163 and 212 prefilled decisions."
        ),
    }
