"""Tests for the untouched 583 to 570 to 450 profile-review lineage."""

import pandas as pd
import pytest

from medical_ratings.profile_eligibility_original_freeze import (
    validate_original_review_lineage,
)


def decision_rows(count: int) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "market": "M",
                "profile_key": f"p:{index}",
                "title": f"Title {index}",
                "address": f"{index} Main St",
                "manual_decision": "",
            }
            for index in range(count)
        ]
    )


def inventory_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Build the minimal source-inventory shape used by the lineage validator."""

    return frame[["market", "profile_key"]].rename(
        columns={"market": "requested_location"}
    )


def test_original_review_lineage_accepts_exact_nested_cohorts() -> None:
    initial = decision_rows(583)
    corrected = initial.iloc[:570].copy()
    rows = corrected.iloc[:450].copy()
    triage = rows.drop(columns="manual_decision")
    groups = pd.DataFrame(
        {
            "review_block_id": [f"b:{index}" for index in range(410)],
            "profile_count": [41] + [1] * 409,
            "group_manual_decision": [""] * 410,
        }
    )
    summary = validate_original_review_lineage(
        initial, corrected, rows, groups, triage, inventory_rows(initial)
    )
    assert summary["canonical_manual_review_profiles"] == 450
    assert summary["canonical_manual_review_profiles_with_decision"] == 0
    assert summary["canonical_review_blocks"] == 410


def test_original_review_lineage_rejects_prefilled_baseline() -> None:
    initial = decision_rows(583)
    corrected = initial.iloc[:570].copy()
    rows = corrected.iloc[:450].copy()
    rows.loc[0, "manual_decision"] = "include_dental_provider"
    groups = pd.DataFrame(
        {
            "review_block_id": [f"b:{index}" for index in range(410)],
            "profile_count": [41] + [1] * 409,
            "group_manual_decision": [""] * 410,
        }
    )
    with pytest.raises(ValueError, match="untouched"):
        validate_original_review_lineage(
            initial,
            corrected,
            rows,
            groups,
            corrected.iloc[:450].drop(columns="manual_decision"),
            inventory_rows(initial),
        )
