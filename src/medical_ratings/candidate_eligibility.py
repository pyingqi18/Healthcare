"""Assign auditable geography and category review statuses to candidates."""

from __future__ import annotations

from typing import Any

import pandas as pd


REQUIRED_CANDIDATE_COLUMNS = {
    "clinic_key",
    "category",
    "market_assignment_status",
}
REQUIRED_RULE_COLUMNS = {
    "category",
    "category_decision",
    "reason",
}
ALLOWED_CATEGORY_DECISIONS = {"include", "exclude", "manual_review"}


def _normalize_category(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.casefold()


def apply_candidate_eligibility_review(
    candidates: pd.DataFrame,
    category_rules: pd.DataFrame,
) -> pd.DataFrame:
    """Return all candidates with review statuses; never silently drop rows."""

    missing_candidates = REQUIRED_CANDIDATE_COLUMNS - set(candidates.columns)
    if missing_candidates:
        raise KeyError(
            f"Candidates are missing columns: {sorted(missing_candidates)}"
        )
    missing_rules = REQUIRED_RULE_COLUMNS - set(category_rules.columns)
    if missing_rules:
        raise KeyError(f"Category rules are missing columns: {sorted(missing_rules)}")
    if candidates.empty:
        raise ValueError("Candidates table is empty")
    if candidates["clinic_key"].isna().any():
        raise ValueError("Candidates contain missing clinic_key values")
    if candidates["clinic_key"].duplicated().any():
        raise ValueError("Candidates contain duplicate clinic_key values")

    rules = category_rules.copy()
    rules["category_key"] = _normalize_category(rules["category"])
    if rules["category_key"].isna().any() or rules["category_key"].eq("").any():
        raise ValueError("Category rules contain blank categories")
    if rules["category_key"].duplicated().any():
        raise ValueError("Category rules contain duplicate categories")
    invalid_decisions = set(rules["category_decision"].dropna()) - (
        ALLOWED_CATEGORY_DECISIONS
    )
    if invalid_decisions:
        raise ValueError(
            f"Category rules contain invalid decisions: {sorted(invalid_decisions)}"
        )

    rule_lookup: dict[str, dict[str, Any]] = {
        str(row["category_key"]): row.to_dict()
        for _, row in rules.iterrows()
    }
    reviewed = candidates.copy()
    statuses: list[str] = []
    reasons: list[str] = []
    category_decisions: list[str | None] = []

    for _, row in reviewed.iterrows():
        geography_status = str(row["market_assignment_status"])
        category = row.get("category")
        category_key = None
        if pd.notna(category) and str(category).strip():
            category_key = str(category).strip().casefold()
        rule = rule_lookup.get(category_key or "")
        category_decision = None if rule is None else str(rule["category_decision"])
        category_decisions.append(category_decision)

        if geography_status == "outside_target_zip":
            statuses.append("exclude_outside_target_zip")
            reasons.append("Maps ZIP is outside the configured target markets")
        elif geography_status == "local_finder_only_unlocated":
            statuses.append("needs_geography")
            reasons.append("Local Finder candidate has no Maps ZIP evidence")
        elif geography_status == "maps_missing_zip":
            statuses.append("needs_geography")
            reasons.append("Maps candidate is missing ZIP evidence")
        elif geography_status != "eligible_target_zip":
            raise ValueError(f"Unknown market assignment status: {geography_status}")
        elif rule is None:
            statuses.append("manual_category_review")
            reasons.append("No configured rule exists for this Google category")
        elif category_decision == "include":
            statuses.append("include_dental_provider")
            reasons.append(str(rule["reason"]))
        elif category_decision == "exclude":
            statuses.append("exclude_non_dentist_category")
            reasons.append(str(rule["reason"]))
        else:
            statuses.append("manual_category_review")
            reasons.append(str(rule["reason"]))

    reviewed["category_rule_decision"] = category_decisions
    reviewed["eligibility_review_status"] = statuses
    reviewed["eligibility_review_reason"] = reasons
    return reviewed
