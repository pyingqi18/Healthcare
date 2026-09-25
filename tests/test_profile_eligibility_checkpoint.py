"""Validate the versioned stage 46 eligibility-decision checkpoint."""

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
VERIFIED_PATH = ROOT / "config/profile_eligibility_verified_decisions_20260925.csv"
REMAINING_PATH = (
    ROOT / "config/profile_eligibility_remaining_decisions_20260925_partial.csv"
)
ALLOWED_DECISIONS = {
    "include_dental_provider",
    "exclude_non_dentist_category",
}
DECISION_FIELDS = {
    "manual_decision",
    "decision_evidence",
    "evidence_url",
    "reviewed_by",
    "reviewed_on",
}


def _clean(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip()


def test_verified_decisions_have_expected_counts() -> None:
    verified = pd.read_csv(VERIFIED_PATH, low_memory=False)
    assert len(verified) == 251
    assert verified["profile_key"].nunique() == 251
    assert verified["manual_decision"].value_counts().to_dict() == {
        "include_dental_provider": 141,
        "exclude_non_dentist_category": 110,
    }
    for column in DECISION_FIELDS:
        assert _clean(verified[column]).ne("").all()


def test_remaining_checkpoint_has_exact_partial_coverage() -> None:
    remaining = pd.read_csv(REMAINING_PATH, low_memory=False)
    assert len(remaining) == 199
    assert remaining["profile_key"].nunique() == 199
    decisions = _clean(remaining["manual_decision"])
    assert decisions.value_counts().to_dict() == {
        "": 134,
        "exclude_non_dentist_category": 61,
        "include_dental_provider": 4,
    }


def test_decided_remaining_rows_have_complete_evidence() -> None:
    remaining = pd.read_csv(REMAINING_PATH, low_memory=False)
    decided = _clean(remaining["manual_decision"]).ne("")
    assert set(_clean(remaining.loc[decided, "manual_decision"])) <= ALLOWED_DECISIONS
    for column in DECISION_FIELDS - {"manual_decision"}:
        assert _clean(remaining.loc[decided, column]).ne("").all()


def test_verified_and_remaining_profiles_are_disjoint() -> None:
    verified = pd.read_csv(VERIFIED_PATH, usecols=["profile_key"])
    remaining = pd.read_csv(REMAINING_PATH, usecols=["profile_key"])
    assert set(verified["profile_key"]).isdisjoint(remaining["profile_key"])
    assert len(verified) + len(remaining) == 450
