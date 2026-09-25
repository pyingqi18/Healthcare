"""Prioritize unresolved singleton profiles by the specificity of saved evidence."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote, urlparse

import pandas as pd


REQUIRED_COLUMNS = {
    "decision_id",
    "market",
    "profile_key",
    "title",
    "address",
    "observed_categories",
    "manual_decision",
    "review_tier",
    "suggested_manual_decision",
    "suggestion_basis",
    "source_phone",
    "source_website_url",
    "normalized_source_domain",
    "direct_profile_evidence_url",
    "review_block_id",
    "review_block_basis",
}

DENTAL_PATH_TERMS = (
    "dental",
    "dentist",
    "dentistry",
    "oral",
    "orthodont",
    "endodont",
    "periodont",
    "maxillofacial",
    "craniofacial",
    "denture",
    "prosthodont",
)
STRUCTURED_PATH_TERMS = (
    "location",
    "provider",
    "doctor",
    "patientcare",
    "patient-care",
    "services",
    "departments-services",
    "find-a-clinic",
)
TITLE_STOP_WORDS = {
    "health",
    "center",
    "centre",
    "clinic",
    "medical",
    "group",
    "care",
    "service",
    "services",
    "community",
    "family",
    "hospital",
    "the",
    "and",
    "inc",
    "new",
    "york",
    "los",
    "angeles",
}


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) >= 4 and token not in TITLE_STOP_WORDS
    }


def _url_path(url: str) -> str:
    value = _text(url)
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return unquote(parsed.path).strip("/").lower()


def _evidence_route(row: pd.Series) -> str:
    website = _text(row["source_website_url"])
    if not website:
        if _text(row["source_phone"]):
            return "phone_and_google_profile"
        return "google_profile_only"

    path = _url_path(website)
    if not path:
        return "official_homepage"
    if any(term in path for term in DENTAL_PATH_TERMS):
        return "direct_dental_service_page"
    path_tokens = _tokens(path)
    title_tokens = _tokens(_text(row["title"]))
    if path_tokens & title_tokens:
        return "named_location_or_provider_page"
    if any(term in path for term in STRUCTURED_PATH_TERMS):
        return "structured_official_page"
    return "other_official_subpage"


def _review_focus(row: pd.Series) -> str:
    route = row["singleton_evidence_route"]
    if route == "direct_dental_service_page":
        return (
            "Confirm that the page describes current patient-facing dental care at the "
            "profile address; the dental URL term is a prioritization signal only."
        )
    if route == "named_location_or_provider_page":
        return (
            "Match the named location or provider page to the exact profile address, then "
            "confirm whether patients can receive dental care there."
        )
    if route == "structured_official_page":
        return (
            "Check the official location, provider, or service page for exact-address "
            "patient-facing dental care."
        )
    if route == "other_official_subpage":
        return (
            "The saved subpage is specific but not self-identifying; verify both identity "
            "and dental service before deciding."
        )
    if route == "official_homepage":
        return (
            "Navigate from the official homepage to the exact location and service list; "
            "organization-wide dental care does not prove this address qualifies."
        )
    if route == "phone_and_google_profile":
        return (
            "Use the exact Google profile and phone as identity evidence; absence of a "
            "saved website is not evidence for exclusion."
        )
    return (
        "Review the exact Google profile and search for current official evidence; a failed "
        "search is not evidence for exclusion."
    )


def prepare_singleton_profile_audit(
    review_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Build a complete pending queue plus a first batch of specific official pages."""

    missing = REQUIRED_COLUMNS - set(review_rows.columns)
    if missing:
        raise ValueError(f"Profile review rows are missing columns: {sorted(missing)}")
    if review_rows["decision_id"].duplicated().any():
        raise ValueError("Profile review rows contain duplicate decision_id values")
    if review_rows["profile_key"].duplicated().any():
        raise ValueError("Profile review rows contain duplicate profile_key values")

    prepared = review_rows.copy()
    for column in REQUIRED_COLUMNS:
        prepared[column] = prepared[column].map(_text)
    pending = prepared.loc[prepared["manual_decision"].eq("")].copy()
    if pending.empty:
        raise ValueError("No unresolved profile eligibility rows were found")
    if pending["review_block_basis"].ne("singleton_profile").any():
        invalid = sorted(
            pending.loc[
                pending["review_block_basis"].ne("singleton_profile"),
                "review_block_id",
            ].unique()
        )
        raise ValueError(
            "Unresolved queue still contains non-singleton review blocks: "
            + ", ".join(invalid)
        )
    if pending["review_block_id"].duplicated().any():
        raise ValueError("Unresolved singleton queue contains a repeated review_block_id")

    pending["singleton_evidence_route"] = pending.apply(_evidence_route, axis=1)
    priority = {
        "direct_dental_service_page": 1,
        "named_location_or_provider_page": 2,
        "structured_official_page": 3,
        "other_official_subpage": 4,
        "official_homepage": 5,
        "phone_and_google_profile": 6,
        "google_profile_only": 7,
    }
    pending["singleton_audit_priority"] = pending["singleton_evidence_route"].map(
        priority
    )
    pending["specific_official_page_batch"] = pending[
        "singleton_evidence_route"
    ].isin(
        {
            "direct_dental_service_page",
            "named_location_or_provider_page",
            "structured_official_page",
        }
    )
    pending["review_focus"] = pending.apply(_review_focus, axis=1)
    pending["audit_manual_decision"] = ""
    pending["audit_decision_evidence"] = ""
    pending["audit_evidence_url"] = ""
    pending["audit_reviewed_by"] = ""
    pending["audit_reviewed_on"] = ""
    pending = pending.sort_values(
        [
            "singleton_audit_priority",
            "market",
            "normalized_source_domain",
            "title",
            "profile_key",
        ],
        kind="stable",
    ).reset_index(drop=True)
    pending.insert(0, "singleton_audit_sequence", range(1, len(pending) + 1))

    priority_batch = pending.loc[pending["specific_official_page_batch"]].copy()
    priority_batch = priority_batch.reset_index(drop=True)
    priority_batch.insert(0, "priority_batch_sequence", range(1, len(priority_batch) + 1))

    route_counts = {
        key: int(value)
        for key, value in pending["singleton_evidence_route"]
        .value_counts()
        .reindex(priority, fill_value=0)
        .items()
    }
    tier_counts = {
        key: int(value)
        for key, value in pending["review_tier"].value_counts().sort_index().items()
    }
    summary = {
        "analysis_status": "v9_singleton_profile_audit_prioritized_not_final",
        "api_requests_submitted": 0,
        "input_profile_rows": int(len(prepared)),
        "already_decided_profiles": int(prepared["manual_decision"].ne("").sum()),
        "remaining_singleton_profiles": int(len(pending)),
        "remaining_non_singleton_profiles": 0,
        "remaining_profiles_with_website": int(
            pending["source_website_url"].ne("").sum()
        ),
        "remaining_profiles_without_website": int(
            pending["source_website_url"].eq("").sum()
        ),
        "specific_official_page_priority_batch": int(len(priority_batch)),
        "remaining_profiles_by_review_tier": tier_counts,
        "remaining_profiles_by_evidence_route": route_counts,
        "automatic_final_decisions_applied": 0,
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
        "decision_rule": (
            "Evidence routes set review order only. Every final include or exclude decision "
            "must be supported for the exact profile and address."
        ),
        "next_required_action": (
            "Review the specific official-page batch first and append only completed exact "
            "profile decisions to the verified decision file."
        ),
    }
    return pending, priority_batch, summary
