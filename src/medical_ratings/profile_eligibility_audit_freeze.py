"""Validate shared-domain decisions and freeze their complete evidence lineage."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd


DECISION_COLUMN_ORDER = [
    "market",
    "profile_key",
    "title",
    "address",
    "manual_decision",
    "decision_evidence",
    "evidence_url",
    "reviewed_by",
    "reviewed_on",
]
DECISION_COLUMNS = set(DECISION_COLUMN_ORDER)
ALLOWED_DECISIONS = {
    "include_dental_provider",
    "exclude_non_dentist_category",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_columns(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.copy()
    for column in cleaned.columns:
        cleaned[column] = cleaned[column].fillna("").astype(str).str.strip()
    return cleaned


def validate_shared_domain_decisions(
    external_profiles: pd.DataFrame,
    decisions: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate exact-profile decisions for every shared-domain audit member."""

    profile_columns = DECISION_COLUMNS | {
        "decision_id",
        "audit_unit_profile_count",
        "review_block_id",
        "normalized_source_domain",
    }
    _require_columns(external_profiles, profile_columns, "external evidence profiles")
    _require_columns(decisions, DECISION_COLUMNS, "shared-domain decisions")
    profiles = _clean(external_profiles)
    reviewed = _clean(decisions)
    shared = profiles.loc[
        pd.to_numeric(profiles["audit_unit_profile_count"], errors="raise").gt(1)
    ].copy()
    if shared.empty:
        raise ValueError("External evidence profiles contain no shared-domain members")
    if shared["profile_key"].duplicated().any():
        raise ValueError("Shared-domain evidence contains duplicate profile keys")
    if reviewed["profile_key"].duplicated().any():
        raise ValueError("Shared-domain decisions contain duplicate profile keys")
    if set(reviewed["profile_key"]) != set(shared["profile_key"]):
        missing = sorted(set(shared["profile_key"]) - set(reviewed["profile_key"]))
        extra = sorted(set(reviewed["profile_key"]) - set(shared["profile_key"]))
        raise ValueError(
            "Shared-domain decision coverage differs from the evidence queue; "
            f"missing={missing}, extra={extra}"
        )

    identity = ["market", "profile_key", "title", "address"]
    expected = shared[identity].sort_values("profile_key", ignore_index=True)
    observed = reviewed[identity].sort_values("profile_key", ignore_index=True)
    if not expected.equals(observed):
        raise ValueError("Shared-domain decision identity fields differ from frozen evidence")
    if not reviewed["manual_decision"].isin(ALLOWED_DECISIONS).all():
        raise ValueError("Shared-domain decisions contain an unsupported manual decision")
    required_text = [
        "decision_evidence",
        "evidence_url",
        "reviewed_by",
        "reviewed_on",
    ]
    for column in required_text:
        if reviewed[column].eq("").any():
            raise ValueError(f"Shared-domain decisions contain blank {column}")
    invalid_dates = pd.to_datetime(reviewed["reviewed_on"], errors="coerce").isna()
    if invalid_dates.any():
        raise ValueError("Shared-domain decisions contain invalid reviewed_on dates")

    context = shared[
        [
            "profile_key",
            "decision_id",
            "review_block_id",
            "normalized_source_domain",
        ]
    ]
    audited = reviewed.merge(context, on="profile_key", how="left", validate="one_to_one")
    audited = audited.sort_values(
        ["normalized_source_domain", "market", "title", "profile_key"],
        kind="stable",
        ignore_index=True,
    )
    summary = {
        "analysis_status": "shared_domain_profile_eligibility_audit_complete",
        "api_requests_submitted": 0,
        "shared_domain_review_units": int(audited["review_block_id"].nunique()),
        "shared_domain_profiles_reviewed": int(len(audited)),
        "include_dental_provider": int(
            audited["manual_decision"].eq("include_dental_provider").sum()
        ),
        "exclude_non_dentist_category": int(
            audited["manual_decision"].eq("exclude_non_dentist_category").sum()
        ),
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
        "decision_boundary": (
            "Every exact profile and address was reviewed separately. Shared-domain "
            "membership was used only to organize evidence navigation."
        ),
    }
    return audited, summary


def merge_verified_decisions(
    existing: pd.DataFrame,
    additions: pd.DataFrame,
) -> pd.DataFrame:
    """Append validated exact-profile decisions without changing earlier records."""

    _require_columns(existing, DECISION_COLUMNS, "verified decisions")
    _require_columns(additions, DECISION_COLUMNS, "decision additions")
    base = _clean(existing[DECISION_COLUMN_ORDER])
    new = _clean(additions[DECISION_COLUMN_ORDER])
    overlap = sorted(set(base["profile_key"]) & set(new["profile_key"]))
    if overlap:
        raise ValueError(f"Verified decisions already contain profile keys: {overlap}")
    combined = pd.concat([base, new], ignore_index=True)
    return combined.sort_values(
        ["market", "title", "address", "profile_key"],
        kind="stable",
        ignore_index=True,
    )
