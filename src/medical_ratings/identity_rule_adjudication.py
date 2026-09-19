"""Apply a complete manual adjudication to broader identity-rule candidates."""

from __future__ import annotations

from typing import Any

import pandas as pd


ALLOWED_DECISIONS = {
    "same_historical_location",
    "renamed_or_relocated_historical_location",
    "different_nearby_location",
    "historical_reference_out_of_scope",
    "historical_location_closed",
    "true_discovery_gap",
    "unresolved",
}
CONFIRMED_MATCH_DECISIONS = {
    "same_historical_location",
    "renamed_or_relocated_historical_location",
}
DENOMINATOR_EXCLUSION_DECISIONS = {
    "historical_reference_out_of_scope",
}
REQUIRED_CANDIDATE_COLUMNS = {
    "market",
    "reference_key",
    "reference_title",
    "candidate_rule_match",
}
REQUIRED_DECISION_COLUMNS = {
    "reference_key",
    "reviewed_reference_title",
    "proposed_decision",
    "decision_evidence",
    "evidence_url",
    "evidence_checked_at_utc",
    "reviewed_by",
}


def _clean_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def apply_identity_rule_adjudication(
    candidates: pd.DataFrame,
    decisions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Join exact reviewed decisions and report the validation result."""

    missing_candidates = REQUIRED_CANDIDATE_COLUMNS - set(candidates.columns)
    if missing_candidates:
        raise KeyError(
            f"Identity candidates are missing: {sorted(missing_candidates)}"
        )
    missing_decisions = REQUIRED_DECISION_COLUMNS - set(decisions.columns)
    if missing_decisions:
        raise KeyError(
            f"Identity decisions are missing: {sorted(missing_decisions)}"
        )
    if candidates.empty:
        raise ValueError("Identity candidate table is empty")

    candidate_frame = candidates.copy()
    decision_frame = decisions.copy()
    for frame in (candidate_frame, decision_frame):
        frame["reference_key"] = _clean_text(frame["reference_key"])
    if candidate_frame["reference_key"].duplicated().any():
        raise ValueError("Identity candidates contain duplicate reference keys")
    if decision_frame["reference_key"].duplicated().any():
        raise ValueError("Identity decisions contain duplicate reference keys")
    if not candidate_frame["candidate_rule_match"].astype(bool).all():
        raise ValueError("Manual validation input contains a non-candidate row")

    for column in REQUIRED_DECISION_COLUMNS:
        decision_frame[column] = _clean_text(decision_frame[column])
        if decision_frame[column].isna().any() or decision_frame[column].eq("").any():
            raise ValueError(f"Identity decisions contain blank {column} values")
    invalid = set(decision_frame["proposed_decision"]) - ALLOWED_DECISIONS
    if invalid:
        raise ValueError(f"Identity decisions contain invalid values: {sorted(invalid)}")

    candidate_keys = set(candidate_frame["reference_key"])
    decision_keys = set(decision_frame["reference_key"])
    if candidate_keys != decision_keys:
        missing = sorted(candidate_keys - decision_keys)[:5]
        unexpected = sorted(decision_keys - candidate_keys)[:5]
        raise ValueError(
            "Identity decision coverage does not match candidates; "
            f"missing={missing}, unexpected={unexpected}"
        )

    expected_titles = candidate_frame.set_index("reference_key")["reference_title"]
    reviewed_titles = decision_frame.set_index("reference_key")[
        "reviewed_reference_title"
    ]
    for reference_key in sorted(candidate_keys):
        if str(expected_titles.loc[reference_key]).strip() != str(
            reviewed_titles.loc[reference_key]
        ).strip():
            raise ValueError(
                f"Reviewed reference title changed for {reference_key}"
            )

    removable = [
        column
        for column in (
            "proposed_decision",
            "decision_evidence",
            "reviewed_by",
            "reviewed_on",
        )
        if column in candidate_frame.columns
    ]
    reviewed = candidate_frame.drop(columns=removable).merge(
        decision_frame,
        on="reference_key",
        how="left",
        validate="one_to_one",
    )
    reviewed["confirmed_identity_match"] = reviewed[
        "proposed_decision"
    ].isin(CONFIRMED_MATCH_DECISIONS)
    reviewed["exclude_from_current_reference_denominator"] = reviewed[
        "proposed_decision"
    ].isin(DENOMINATOR_EXCLUSION_DECISIONS)
    reviewed["requires_further_review"] = reviewed["proposed_decision"].eq(
        "unresolved"
    )

    confirmed = reviewed.loc[reviewed["confirmed_identity_match"]].copy()
    exclusions = reviewed.loc[
        reviewed["exclude_from_current_reference_denominator"]
    ].copy()
    reviewed_count = len(reviewed)
    confirmed_count = len(confirmed)
    raw_ppv = confirmed_count / reviewed_count
    summary = {
        "analysis_status": "identity_rule_manual_adjudication_complete_not_generalized",
        "api_requests_submitted": 0,
        "reviewed_candidate_rule_units": reviewed_count,
        "manual_decisions_by_status": {
            str(key): int(value)
            for key, value in reviewed["proposed_decision"]
            .value_counts()
            .sort_index()
            .items()
        },
        "confirmed_historical_location_matches": confirmed_count,
        "reference_denominator_exclusions": len(exclusions),
        "remaining_unresolved": int(reviewed["requires_further_review"].sum()),
        "candidate_rule_positive_predictive_value": raw_ppv,
        "candidate_rule_precision_gate": 0.95,
        "candidate_rule_generalization_approved": raw_ppv >= 0.95,
        "automatic_profile_or_location_merges": 0,
        "interpretation": (
            "Only exact manually reviewed reference keys may be applied. "
            "The broader rule is not approved for automatic generalization."
        ),
    }
    return reviewed, confirmed, exclusions, summary
