"""Apply documented pilot candidate and legacy-reference decisions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


REVIEW_STATUSES = {"manual_category_review", "exclude_non_dentist_category"}
CANDIDATE_ACTIONS = {"include", "exclude"}
REFERENCE_BENCHMARK_ACTIONS = {"retain_current", "exclude_current"}
REFERENCE_HISTORY_ACTIONS = {"retain_history", "exclude_history"}


def _require_unique_nonblank(frame: pd.DataFrame, column: str, label: str) -> None:
    if column not in frame.columns:
        raise KeyError(f"{label} is missing {column}")
    values = frame[column].astype("string").str.strip()
    if values.isna().any() or values.eq("").any() or values.duplicated().any():
        raise ValueError(f"{label} requires unique nonblank {column} values")


def adjudicate_pilot_candidates(
    eligibility: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    """Assign separate competition-location and rating-profile actions."""

    required = {
        "clinic_key",
        "title",
        "market_assignment_status",
        "eligibility_review_status",
    }
    missing = required - set(eligibility.columns)
    if missing:
        raise KeyError(f"Eligibility table is missing columns: {sorted(missing)}")
    decision_required = {
        "clinic_key",
        "competition_candidate_action",
        "outcome_profile_action",
        "manual_reason",
        "evidence_url",
        "evidence_checked_at_utc",
    }
    decision_missing = decision_required - set(decisions.columns)
    if decision_missing:
        raise KeyError(f"Candidate decisions are missing columns: {sorted(decision_missing)}")
    _require_unique_nonblank(eligibility, "clinic_key", "Eligibility table")
    _require_unique_nonblank(decisions, "clinic_key", "Candidate decisions")

    target_review = eligibility.loc[
        eligibility["market_assignment_status"].eq("eligible_target_zip")
        & eligibility["eligibility_review_status"].isin(REVIEW_STATUSES),
        "clinic_key",
    ].astype(str)
    decision_keys = set(decisions["clinic_key"].astype(str))
    expected_keys = set(target_review)
    if decision_keys != expected_keys:
        raise ValueError(
            "Candidate decisions must exactly cover target-ZIP manual/excluded profiles; "
            f"missing={sorted(expected_keys - decision_keys)}, "
            f"extra={sorted(decision_keys - expected_keys)}"
        )
    for column in ("competition_candidate_action", "outcome_profile_action"):
        invalid = set(decisions[column].dropna().astype(str)) - CANDIDATE_ACTIONS
        if invalid:
            raise ValueError(f"Invalid {column}: {sorted(invalid)}")

    decision_columns = list(decision_required)
    frame = eligibility.merge(
        decisions[decision_columns], on="clinic_key", how="left", validate="one_to_one"
    )
    target = frame["market_assignment_status"].eq("eligible_target_zip")
    automatic = target & frame["eligibility_review_status"].eq("include_dental_provider")
    frame.loc[automatic, "competition_candidate_action"] = "include"
    frame.loc[automatic, "outcome_profile_action"] = "include"
    frame.loc[~target, "competition_candidate_action"] = "out_of_scope"
    frame.loc[~target, "outcome_profile_action"] = "out_of_scope"
    if frame.loc[target, ["competition_candidate_action", "outcome_profile_action"]].isna().any().any():
        raise ValueError("Every target-ZIP candidate must receive both final actions")
    frame["competition_candidate_included"] = frame[
        "competition_candidate_action"
    ].eq("include")
    frame["outcome_profile_included"] = frame["outcome_profile_action"].eq("include")
    return frame


def adjudicate_reference_locations(
    reference_matches: pd.DataFrame,
    match_pairs: pd.DataFrame,
    adjudicated_candidates: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    """Separate current-discovery benchmark decisions from historical retention."""

    required = {"reference_key", "market", "reference_title", "discovered"}
    missing = required - set(reference_matches.columns)
    if missing:
        raise KeyError(f"Reference matches are missing columns: {sorted(missing)}")
    pair_required = {"reference_key", "candidate_key", "fixed_rule_match"}
    pair_missing = pair_required - set(match_pairs.columns)
    if pair_missing:
        raise KeyError(f"Reference match pairs are missing columns: {sorted(pair_missing)}")
    decision_required = {
        "reference_key",
        "current_benchmark_action",
        "historical_panel_action",
        "manual_reason",
        "evidence_url",
        "evidence_checked_at_utc",
    }
    decision_missing = decision_required - set(decisions.columns)
    if decision_missing:
        raise KeyError(f"Reference decisions are missing columns: {sorted(decision_missing)}")
    _require_unique_nonblank(reference_matches, "reference_key", "Reference matches")
    _require_unique_nonblank(decisions, "reference_key", "Reference decisions")

    unmatched = set(
        reference_matches.loc[~reference_matches["discovered"].astype(bool), "reference_key"]
        .astype(str)
    )
    decision_keys = set(decisions["reference_key"].astype(str))
    if decision_keys != unmatched:
        raise ValueError(
            "Reference decisions must exactly cover unmatched references; "
            f"missing={sorted(unmatched - decision_keys)}, extra={sorted(decision_keys - unmatched)}"
        )
    invalid_current = (
        set(decisions["current_benchmark_action"].dropna().astype(str))
        - REFERENCE_BENCHMARK_ACTIONS
    )
    invalid_history = (
        set(decisions["historical_panel_action"].dropna().astype(str))
        - REFERENCE_HISTORY_ACTIONS
    )
    if invalid_current or invalid_history:
        raise ValueError(
            f"Invalid reference actions: current={sorted(invalid_current)}, "
            f"history={sorted(invalid_history)}"
        )

    frame = reference_matches.merge(
        decisions[list(decision_required)],
        on="reference_key",
        how="left",
        validate="one_to_one",
    )
    discovered = frame["discovered"].astype(bool)
    frame.loc[discovered, "current_benchmark_action"] = "retain_current"
    frame.loc[discovered, "historical_panel_action"] = "retain_history"
    frame["current_benchmark_included"] = frame["current_benchmark_action"].eq(
        "retain_current"
    )
    frame["historical_panel_included"] = frame["historical_panel_action"].eq(
        "retain_history"
    )

    candidate_actions = adjudicated_candidates.set_index("clinic_key")[[
        "competition_candidate_included",
        "outcome_profile_included",
    ]]
    pairs = match_pairs.loc[match_pairs["fixed_rule_match"].astype(bool)].copy()
    pairs = pairs.merge(
        candidate_actions,
        left_on="candidate_key",
        right_index=True,
        how="left",
        validate="many_to_one",
    )
    if pairs[["competition_candidate_included", "outcome_profile_included"]].isna().any().any():
        raise ValueError("Match pairs contain candidate keys absent from adjudicated candidates")
    pair_summary = pairs.groupby("reference_key", as_index=False).agg(
        discovered_with_competition_candidate=("competition_candidate_included", "max"),
        discovered_with_outcome_profile=("outcome_profile_included", "max"),
    )
    frame = frame.merge(pair_summary, on="reference_key", how="left", validate="one_to_one")
    for column in (
        "discovered_with_competition_candidate",
        "discovered_with_outcome_profile",
    ):
        frame[column] = frame[column].astype("boolean").fillna(False).astype(bool)
    return frame


def summarize_manual_audit(
    candidates: pd.DataFrame,
    references: pd.DataFrame,
) -> dict[str, Any]:
    """Summarize final pilot manual decisions without changing source rows."""

    target = candidates["market_assignment_status"].eq("eligible_target_zip")
    benchmark = references["current_benchmark_included"].astype(bool)
    benchmark_count = int(benchmark.sum())
    competition_found = int(
        references.loc[benchmark, "discovered_with_competition_candidate"].sum()
    )
    outcome_found = int(
        references.loc[benchmark, "discovered_with_outcome_profile"].sum()
    )
    return {
        "analysis_status": "pilot_manual_evidence_audit_complete",
        "api_requests_submitted": 0,
        "automatic_profile_or_location_merges": 0,
        "target_zip_profiles": int(target.sum()),
        "competition_candidates_included": int(
            candidates.loc[target, "competition_candidate_included"].sum()
        ),
        "outcome_profiles_included": int(
            candidates.loc[target, "outcome_profile_included"].sum()
        ),
        "manually_adjudicated_profiles": int(
            candidates.loc[target, "manual_reason"].notna().sum()
        ),
        "current_reference_benchmark_count": benchmark_count,
        "current_reference_exclusions": int((~benchmark).sum()),
        "historical_references_retained": int(
            references["historical_panel_included"].sum()
        ),
        "competition_discovery_count": competition_found,
        "competition_discovery_recall": competition_found / benchmark_count,
        "outcome_profile_discovery_count": outcome_found,
        "outcome_profile_discovery_recall": outcome_found / benchmark_count,
        "valid_current_references_not_discovered": references.loc[
            benchmark & ~references["discovered_with_competition_candidate"],
            "reference_key",
        ].astype(str).tolist(),
        "decision": "approve_business_listings_as_primary_with_validated_legacy_carry_forward",
        "interpretation": (
            "Current discovery eligibility, rating-profile eligibility, and historical-panel "
            "retention are separate decisions."
        ),
    }
