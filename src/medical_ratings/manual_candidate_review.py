"""Apply a complete, auditable decision set to unresolved clinic candidates."""

from __future__ import annotations

import pandas as pd


UNRESOLVED_STATUSES = {"manual_category_review", "needs_geography"}
ALLOWED_MANUAL_DECISIONS = {
    "include_dental_provider",
    "exclude_non_dentist_category",
    "exclude_unverified_geography",
}
REQUIRED_CANDIDATE_COLUMNS = {
    "clinic_key",
    "cid",
    "title",
    "mapped_location",
    "eligibility_review_status",
}
REQUIRED_DECISION_COLUMNS = {
    "clinic_key",
    "cid",
    "reviewed_title",
    "manual_decision",
    "manual_reason",
    "evidence_url",
    "evidence_checked_at_utc",
}


def _normalized_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def apply_manual_candidate_decisions(
    candidates: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    """Resolve every currently unresolved row without dropping any candidate."""

    missing_candidates = REQUIRED_CANDIDATE_COLUMNS - set(candidates.columns)
    if missing_candidates:
        raise KeyError(
            f"Candidates are missing columns: {sorted(missing_candidates)}"
        )
    missing_decisions = REQUIRED_DECISION_COLUMNS - set(decisions.columns)
    if missing_decisions:
        raise KeyError(
            f"Manual decisions are missing columns: {sorted(missing_decisions)}"
        )
    if candidates.empty:
        raise ValueError("Candidates table is empty")

    candidate_frame = candidates.copy()
    decision_frame = decisions.copy()
    for frame in (candidate_frame, decision_frame):
        frame["clinic_key"] = _normalized_text(frame["clinic_key"])
        frame["cid"] = _normalized_text(frame["cid"])

    if candidate_frame["clinic_key"].isna().any():
        raise ValueError("Candidates contain missing clinic_key values")
    if candidate_frame["clinic_key"].duplicated().any():
        raise ValueError("Candidates contain duplicate clinic_key values")
    if candidate_frame["cid"].duplicated().any():
        raise ValueError("Candidates contain duplicate CID values")
    if decision_frame["clinic_key"].duplicated().any():
        raise ValueError("Manual decisions contain duplicate clinic_key values")
    if decision_frame["cid"].duplicated().any():
        raise ValueError("Manual decisions contain duplicate CID values")

    for column in (
        "clinic_key",
        "cid",
        "reviewed_title",
        "manual_decision",
        "manual_reason",
        "evidence_url",
        "evidence_checked_at_utc",
    ):
        values = _normalized_text(decision_frame[column])
        if values.isna().any() or values.eq("").any():
            raise ValueError(f"Manual decisions contain blank {column} values")
        decision_frame[column] = values

    invalid_decisions = set(decision_frame["manual_decision"]) - (
        ALLOWED_MANUAL_DECISIONS
    )
    if invalid_decisions:
        raise ValueError(
            f"Manual decisions contain invalid values: {sorted(invalid_decisions)}"
        )

    unresolved = candidate_frame.loc[
        candidate_frame["eligibility_review_status"].isin(UNRESOLVED_STATUSES)
    ]
    expected_keys = set(unresolved["clinic_key"])
    decision_keys = set(decision_frame["clinic_key"])
    if decision_keys != expected_keys:
        missing = sorted(expected_keys - decision_keys)[:5]
        unexpected = sorted(decision_keys - expected_keys)[:5]
        raise ValueError(
            "Manual decision coverage does not match unresolved candidates; "
            f"missing={missing}, unexpected={unexpected}"
        )

    expected_identity = unresolved.set_index("clinic_key")[["cid", "title"]]
    supplied_identity = decision_frame.set_index("clinic_key")[
        ["cid", "reviewed_title"]
    ]
    for clinic_key in sorted(expected_keys):
        expected_cid = str(expected_identity.loc[clinic_key, "cid"]).strip()
        supplied_cid = str(supplied_identity.loc[clinic_key, "cid"]).strip()
        if supplied_cid != expected_cid:
            raise ValueError(f"Manual decision CID mismatch for {clinic_key}")
        expected_title = str(expected_identity.loc[clinic_key, "title"]).strip()
        supplied_title = str(
            supplied_identity.loc[clinic_key, "reviewed_title"]
        ).strip()
        if supplied_title != expected_title:
            raise ValueError(f"Manual decision title mismatch for {clinic_key}")

    reviewed = candidate_frame.merge(
        decision_frame,
        on=["clinic_key", "cid"],
        how="left",
        validate="one_to_one",
    )
    reviewed["previous_eligibility_review_status"] = reviewed[
        "eligibility_review_status"
    ]
    apply_mask = reviewed["manual_decision"].notna()
    reviewed.loc[apply_mask, "eligibility_review_status"] = reviewed.loc[
        apply_mask, "manual_decision"
    ]
    reviewed.loc[apply_mask, "eligibility_review_reason"] = reviewed.loc[
        apply_mask, "manual_reason"
    ]
    reviewed["manual_review_applied"] = apply_mask
    reviewed["final_included"] = reviewed["eligibility_review_status"].eq(
        "include_dental_provider"
    )

    remaining = reviewed["eligibility_review_status"].isin(UNRESOLVED_STATUSES)
    if remaining.any():
        raise ValueError("Unresolved candidates remain after manual review")
    if len(reviewed) != len(candidate_frame):
        raise ValueError("Candidate row count changed during manual review")
    return reviewed
