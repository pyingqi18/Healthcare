"""Prepare and apply one consolidated audit for all remaining profiles."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

import pandas as pd

from medical_ratings.profile_eligibility_audit_freeze import (
    ALLOWED_DECISIONS,
    DECISION_COLUMN_ORDER,
    merge_verified_decisions,
)


IDENTITY_COLUMNS = ["market", "profile_key", "title", "address"]
FINAL_REVIEW_COLUMNS = [
    "manual_decision",
    "decision_evidence",
    "evidence_url",
    "reviewed_by",
    "reviewed_on",
]


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        result[column] = result[column].fillna("").astype(str).str.strip()
    return result


def _require(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def _title_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _search_url(title: str, address: str, suffix: str = "dental") -> str:
    query = f'"{title}" "{address}" {suffix}'.strip()
    return "https://www.google.com/search?q=" + quote_plus(query)


def prepare_remaining_completion(
    remaining: pd.DataFrame,
    verified_decisions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Build one exact-profile decision table and a compact organization index."""

    required = set(IDENTITY_COLUMNS) | {
        "singleton_audit_sequence",
        "observed_sources",
        "observed_categories",
        "source_phone",
        "source_domain",
        "source_website_url",
        "direct_profile_evidence_url",
    }
    _require(remaining, required, "remaining singleton audit")
    _require(
        verified_decisions,
        set(DECISION_COLUMN_ORDER),
        "verified decisions",
    )
    queue = _clean(remaining)
    verified = _clean(verified_decisions)
    if queue["profile_key"].duplicated().any():
        raise ValueError("Remaining singleton audit contains duplicate profile keys")
    if verified["profile_key"].duplicated().any():
        raise ValueError("Verified decisions contain duplicate profile keys")
    overlap = sorted(set(queue["profile_key"]) & set(verified["profile_key"]))
    if overlap:
        raise ValueError(f"Remaining and verified profile keys overlap: {overlap[:10]}")
    decision_fields = [column for column in FINAL_REVIEW_COLUMNS if column in queue]
    if decision_fields and queue[decision_fields].ne("").any(axis=None):
        raise ValueError("Remaining singleton audit already contains final decisions")

    records: list[dict[str, str]] = []
    for row in queue.itertuples(index=False):
        domain = row.source_domain or ""
        organization_key = domain.casefold() if domain else _title_key(row.title)
        if row.source_website_url:
            route = "official_site_and_exact_profile"
        elif row.source_phone:
            route = "phone_and_exact_profile"
        else:
            route = "exact_profile_only"
        records.append(
            {
                "completion_sequence": str(row.singleton_audit_sequence),
                "market": row.market,
                "profile_key": row.profile_key,
                "title": row.title,
                "address": row.address,
                "observed_sources": row.observed_sources,
                "observed_categories": row.observed_categories,
                "source_phone": row.source_phone,
                "source_domain": domain,
                "official_site_url": row.source_website_url,
                "exact_google_profile_url": row.direct_profile_evidence_url,
                "exact_title_address_search_url": _search_url(row.title, row.address),
                "organization_key": organization_key,
                "evidence_route": route,
                "manual_decision": "",
                "decision_evidence": "",
                "evidence_url": "",
                "reviewed_by": "",
                "reviewed_on": "",
            }
        )
    decisions = pd.DataFrame.from_records(records).sort_values(
        ["completion_sequence"], key=lambda s: pd.to_numeric(s), ignore_index=True
    )
    groups = (
        decisions.groupby(["organization_key", "source_domain"], dropna=False)
        .agg(
            profile_count=("profile_key", "size"),
            markets=("market", lambda s: "|".join(sorted(set(s)))),
            titles=("title", lambda s: " || ".join(s)),
            completion_sequences=(
                "completion_sequence",
                lambda s: "|".join(str(value) for value in s),
            ),
        )
        .reset_index()
        .sort_values(
            ["profile_count", "organization_key"],
            ascending=[False, True],
            ignore_index=True,
        )
    )
    summary = {
        "analysis_status": "remaining_profile_completion_prepared",
        "api_requests_submitted": 0,
        "verified_decisions_before": int(len(verified)),
        "remaining_profiles": int(len(decisions)),
        "final_profile_count_after_completion": int(len(verified) + len(decisions)),
        "profiles_with_official_site": int(decisions["official_site_url"].ne("").sum()),
        "profiles_with_phone": int(decisions["source_phone"].ne("").sum()),
        "exact_google_profile_links": int(
            decisions["exact_google_profile_url"].ne("").sum()
        ),
        "organization_review_units": int(len(groups)),
        "automatic_final_decisions_applied": 0,
        "next_required_action": (
            "Complete the five decision fields in remaining_profile_decisions.csv, "
            "then rerun the same script with --decisions."
        ),
    }
    return decisions, groups, summary


def apply_remaining_completion(
    remaining: pd.DataFrame,
    prepared_decisions: pd.DataFrame,
    reviewed_decisions: pd.DataFrame,
    verified_decisions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Validate full remaining coverage and append it to the verified freeze."""

    _require(
        prepared_decisions,
        set(IDENTITY_COLUMNS + FINAL_REVIEW_COLUMNS)
        | {"completion_sequence", "profile_key"},
        "prepared decisions",
    )
    _require(
        reviewed_decisions,
        set(IDENTITY_COLUMNS + FINAL_REVIEW_COLUMNS)
        | {"completion_sequence", "profile_key"},
        "reviewed decisions",
    )
    prepared = _clean(prepared_decisions)
    reviewed = _clean(reviewed_decisions)
    if reviewed["profile_key"].duplicated().any():
        raise ValueError("Reviewed decisions contain duplicate profile keys")
    if set(prepared["profile_key"]) != set(reviewed["profile_key"]):
        missing = sorted(set(prepared["profile_key"]) - set(reviewed["profile_key"]))
        extra = sorted(set(reviewed["profile_key"]) - set(prepared["profile_key"]))
        raise ValueError(
            "Reviewed decisions do not exactly cover the prepared queue; "
            f"missing={missing[:10]}, extra={extra[:10]}"
        )
    expected = prepared.set_index("profile_key")
    observed = reviewed.set_index("profile_key").reindex(expected.index)
    identity_check = ["completion_sequence", "market", "title", "address"]
    if not expected[identity_check].equals(observed[identity_check]):
        raise ValueError("Reviewed decision identities differ from the prepared queue")
    invalid = sorted(set(reviewed["manual_decision"]) - ALLOWED_DECISIONS)
    if invalid:
        raise ValueError(f"Reviewed decisions contain invalid values: {invalid}")
    blank = reviewed[FINAL_REVIEW_COLUMNS].eq("").any(axis=1)
    if blank.any():
        raise ValueError(
            "Reviewed decisions have incomplete decision fields for "
            f"{int(blank.sum())} profiles"
        )

    additions = reviewed[IDENTITY_COLUMNS + FINAL_REVIEW_COLUMNS].copy()
    additions = additions[DECISION_COLUMN_ORDER].sort_values(
        ["market", "title", "profile_key"], kind="stable", ignore_index=True
    )
    combined = merge_verified_decisions(verified_decisions, additions)
    expected_total = len(verified_decisions) + len(remaining)
    if len(combined) != expected_total:
        raise ValueError(
            f"Completed decision count {len(combined)} differs from {expected_total}"
        )
    summary = {
        "analysis_status": "profile_eligibility_completion_applied",
        "api_requests_submitted": 0,
        "reviewed_remaining_profiles": int(len(additions)),
        "verified_decisions_before": int(len(verified_decisions)),
        "verified_decisions_after": int(len(combined)),
        "included_profiles_total": int(
            combined["manual_decision"].eq("include_dental_provider").sum()
        ),
        "excluded_profiles_total": int(
            combined["manual_decision"].eq("exclude_non_dentist_category").sum()
        ),
        "remaining_unresolved": 0,
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
        "next_required_action": (
            "Load the completed 450-profile verified freeze into 46c, apply the "
            "completed eligibility review, and pass its decision file to 46a."
        ),
    }
    return additions, combined, summary
