"""Build a compact, non-decisional audit queue for external profile evidence."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import quote_plus

import pandas as pd


EXTERNAL_REVIEW_TIER = "external_evidence_required"
REQUIRED_COLUMNS = {
    "decision_id",
    "market",
    "profile_key",
    "title",
    "address",
    "observed_categories",
    "manual_decision",
    "review_tier",
    "source_phone",
    "source_website_url",
    "normalized_source_domain",
    "review_block_id",
    "direct_profile_evidence_url",
}


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _join_unique(values: Iterable[Any], separator: str = " || ") -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = _text(value)
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return separator.join(ordered)


def _search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def _profile_search_query(row: pd.Series) -> str:
    quoted = [
        f'"{value}"'
        for value in [_text(row["title"]), _text(row["address"]), _text(row["source_phone"])]
        if value
    ]
    return " ".join(quoted + ["dentist dental patients"])


def _site_search_query(row: pd.Series) -> str:
    domain = _text(row["normalized_source_domain"])
    if not domain:
        return ""
    title = _text(row["title"])
    return f'site:{domain} "{title}" dental dentist patients'


def _route_for_row(row: pd.Series) -> str:
    if int(row["audit_unit_profile_count"]) > 1:
        return "shared_domain_block"
    if _text(row["source_website_url"]):
        return "direct_website_singleton"
    if _text(row["source_phone"]):
        return "phone_and_profile_singleton"
    return "profile_only_singleton"


def prepare_external_evidence_audit(
    review_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return unit, profile, and domain queues without making eligibility decisions."""

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
    pending = prepared.loc[
        prepared["manual_decision"].eq("")
        & prepared["review_tier"].eq(EXTERNAL_REVIEW_TIER)
    ].copy()
    if pending.empty:
        raise ValueError("No unresolved external-evidence profiles were found")
    if pending["review_block_id"].eq("").any():
        raise ValueError("External-evidence profiles contain blank review_block_id values")

    block_counts = pending.groupby("review_block_id")["profile_key"].size()
    pending["audit_unit_profile_count"] = pending["review_block_id"].map(block_counts)
    multi = pending["audit_unit_profile_count"].gt(1)
    invalid_multi = pending.loc[multi].groupby("review_block_id").filter(
        lambda group: (
            group["normalized_source_domain"].eq("").any()
            or group["normalized_source_domain"].nunique() != 1
        )
    )
    if not invalid_multi.empty:
        raise ValueError(
            "Multi-profile external-evidence blocks must share one nonblank domain"
        )

    pending["evidence_route"] = pending.apply(_route_for_row, axis=1)
    priority = {
        "shared_domain_block": 1,
        "direct_website_singleton": 2,
        "phone_and_profile_singleton": 3,
        "profile_only_singleton": 4,
    }
    pending["audit_priority"] = pending["evidence_route"].map(priority).astype(int)
    pending["profile_search_query"] = pending.apply(_profile_search_query, axis=1)
    pending["profile_search_url"] = pending["profile_search_query"].map(_search_url)
    pending["official_site_search_query"] = pending.apply(_site_search_query, axis=1)
    pending["official_site_search_url"] = pending["official_site_search_query"].map(
        lambda value: _search_url(value) if value else ""
    )
    pending["audit_rule"] = (
        "Verify current patient-facing dental service for this exact profile and address; "
        "a shared domain alone is not a decision."
    )
    pending = pending.sort_values(
        ["audit_priority", "normalized_source_domain", "market", "title", "profile_key"],
        kind="stable",
    ).reset_index(drop=True)
    pending.insert(0, "profile_audit_sequence", range(1, len(pending) + 1))

    unit_rows: list[dict[str, Any]] = []
    for block_id, group in pending.groupby("review_block_id", sort=False):
        first = group.iloc[0]
        unit_rows.append(
            {
                "audit_unit_id": block_id,
                "audit_priority": int(group["audit_priority"].min()),
                "evidence_route": _text(first["evidence_route"]),
                "profile_count": len(group),
                "markets": _join_unique(group["market"]),
                "normalized_source_domain": _join_unique(
                    group["normalized_source_domain"]
                ),
                "profile_keys": _join_unique(group["profile_key"]),
                "titles": _join_unique(group["title"]),
                "addresses": _join_unique(group["address"]),
                "observed_categories": _join_unique(group["observed_categories"]),
                "source_website_urls": _join_unique(group["source_website_url"]),
                "source_phones": _join_unique(group["source_phone"]),
                "direct_profile_evidence_urls": _join_unique(
                    group["direct_profile_evidence_url"]
                ),
                "official_site_search_urls": _join_unique(
                    group["official_site_search_url"]
                ),
                "profile_search_urls": _join_unique(group["profile_search_url"]),
                "decision_boundary": (
                    "Review every member. Use one block decision only when the same "
                    "evidence supports every exact profile; otherwise review profiles separately."
                ),
            }
        )
    units = pd.DataFrame.from_records(unit_rows).sort_values(
        ["audit_priority", "normalized_source_domain", "markets", "titles"],
        kind="stable",
    ).reset_index(drop=True)
    units.insert(0, "audit_unit_sequence", range(1, len(units) + 1))

    domain_source = pending.loc[pending["normalized_source_domain"].ne("")].copy()
    domain_rows: list[dict[str, Any]] = []
    for domain, group in domain_source.groupby("normalized_source_domain", sort=True):
        domain_rows.append(
            {
                "normalized_source_domain": domain,
                "profile_count": len(group),
                "review_block_count": group["review_block_id"].nunique(),
                "market_count": group["market"].nunique(),
                "markets": _join_unique(group["market"]),
                "titles": _join_unique(group["title"]),
                "observed_categories": _join_unique(group["observed_categories"]),
                "website_urls": _join_unique(group["source_website_url"]),
                "site_search_url": _search_url(
                    f"site:{domain} dental dentist patients locations"
                ),
                "reuse_boundary": (
                    "Domain evidence may be reused as a navigation aid only; each exact "
                    "profile and address still needs a supported decision."
                ),
            }
        )
    domains = pd.DataFrame.from_records(domain_rows)
    if not domains.empty:
        domains = domains.sort_values(
            ["profile_count", "review_block_count", "normalized_source_domain"],
            ascending=[False, False, True],
            kind="stable",
        ).reset_index(drop=True)
        domains.insert(0, "domain_audit_sequence", range(1, len(domains) + 1))

    route_profile_counts = {
        key: int(value)
        for key, value in pending["evidence_route"].value_counts().sort_index().items()
    }
    route_unit_counts = {
        key: int(value)
        for key, value in units["evidence_route"].value_counts().sort_index().items()
    }
    summary = {
        "analysis_status": "external_profile_evidence_audit_queue_prepared_not_final",
        "api_requests_submitted": 0,
        "input_profile_rows": int(len(prepared)),
        "already_decided_profiles": int(prepared["manual_decision"].ne("").sum()),
        "remaining_profile_rows": int(prepared["manual_decision"].eq("").sum()),
        "external_evidence_profiles": int(len(pending)),
        "external_evidence_audit_units": int(len(units)),
        "shared_domain_audit_units": int((units["profile_count"] > 1).sum()),
        "profiles_in_shared_domain_audit_units": int(
            units.loc[units["profile_count"] > 1, "profile_count"].sum()
        ),
        "singleton_audit_units": int((units["profile_count"] == 1).sum()),
        "profiles_with_saved_website": int(pending["source_website_url"].ne("").sum()),
        "profiles_with_phone": int(pending["source_phone"].ne("").sum()),
        "profiles_with_website_or_phone": int(
            (pending["source_website_url"].ne("") | pending["source_phone"].ne("")).sum()
        ),
        "profiles_without_website_or_phone": int(
            (pending["source_website_url"].eq("") & pending["source_phone"].eq("")).sum()
        ),
        "unique_nonblank_domains": int(pending["normalized_source_domain"].replace("", pd.NA).nunique()),
        "profiles_by_evidence_route": route_profile_counts,
        "audit_units_by_evidence_route": route_unit_counts,
        "automatic_final_decisions_applied": 0,
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
        "next_required_action": (
            "Audit shared-domain units first, then direct-website singletons. Record "
            "only exact profile decisions supported by current patient-facing evidence."
        ),
    }
    return units, pending, domains, summary
