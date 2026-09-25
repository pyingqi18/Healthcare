"""Prepare and apply audited row and group profile-eligibility decisions."""

from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd


ALLOWED_FINAL_DECISIONS = {
    "include_dental_provider",
    "exclude_non_dentist_category",
}
GROUP_REVIEW_ACTIONS = ALLOWED_FINAL_DECISIONS | {"individual_review"}

ROW_IDENTITY_COLUMNS = [
    "decision_id",
    "market",
    "profile_key",
    "title",
    "address",
    "observed_sources",
    "observed_categories",
    "observed_source_decisions",
    "profile_status_basis",
    "allowed_manual_decisions",
]
ROW_REVIEW_COLUMNS = [
    "manual_decision",
    "decision_evidence",
    "evidence_url",
    "reviewed_by",
    "reviewed_on",
]
VERIFIED_DECISION_COLUMNS = [
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


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _profile_evidence_url(profile_key: Any) -> str:
    key = _text(profile_key)
    if key.startswith("google:cid:"):
        cid = key.removeprefix("google:cid:")
        return f"https://www.google.com/maps?cid={cid}"
    if key.startswith("google:place_id:"):
        place_id = key.removeprefix("google:place_id:")
        return (
            "https://www.google.com/maps/search/?api=1&query=Google"
            f"&query_place_id={place_id}"
        )
    return ""


def _review_block_id(*values: Any) -> str:
    payload = "\x1f".join(_text(value) for value in values)
    return "eligibility_review_block:" + hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:16]


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{label} is missing columns: {sorted(missing)}")


def _assert_unique(frame: pd.DataFrame, column: str, label: str) -> None:
    if frame[column].duplicated().any():
        raise ValueError(f"{label} contains duplicate {column} values")


def _apply_verified_decisions(
    row_review: pd.DataFrame,
    verified_decisions: pd.DataFrame | None,
) -> pd.DataFrame:
    """Prefill exact, externally verified profile decisions with identity guards."""

    reviewed = row_review.copy()
    reviewed["verified_decision_applied"] = False
    if verified_decisions is None or verified_decisions.empty:
        return reviewed

    _require_columns(
        verified_decisions,
        set(VERIFIED_DECISION_COLUMNS),
        "Verified profile decisions",
    )
    _assert_unique(
        verified_decisions,
        "profile_key",
        "Verified profile decisions",
    )
    lookup = reviewed.set_index("profile_key", drop=False)
    missing = sorted(set(verified_decisions["profile_key"]) - set(lookup.index))
    if missing:
        raise ValueError(
            "Verified profile decisions are missing from the current review rows: "
            + ", ".join(missing[:10])
        )

    for decision in verified_decisions.itertuples(index=False):
        profile_key = _text(decision.profile_key)
        current = lookup.loc[profile_key]
        for column in ["market", "title", "address"]:
            expected = _text(getattr(decision, column))
            actual = _text(current[column])
            if expected != actual:
                raise ValueError(
                    f"Verified decision identity drift for {profile_key}: "
                    f"{column} is {actual!r}, expected {expected!r}"
                )
        manual_decision = _text(decision.manual_decision)
        if manual_decision not in ALLOWED_FINAL_DECISIONS:
            raise ValueError(
                f"Invalid verified decision for {profile_key}: {manual_decision}"
            )
        allowed = set(_text(current["allowed_manual_decisions"]).split("|"))
        if manual_decision not in allowed:
            raise ValueError(
                f"Verified decision {manual_decision} is not allowed for {profile_key}"
            )
        for column in [
            "decision_evidence",
            "evidence_url",
            "reviewed_by",
            "reviewed_on",
        ]:
            if not _text(getattr(decision, column)):
                raise ValueError(
                    f"Verified decision for {profile_key} is missing {column}"
                )
        mask = reviewed["profile_key"].eq(profile_key)
        for column in ROW_REVIEW_COLUMNS:
            reviewed.loc[mask, column] = _text(getattr(decision, column))
        reviewed.loc[mask, "verified_decision_applied"] = True
    return reviewed


def prepare_profile_eligibility_review(
    triage: pd.DataFrame,
    groups: pd.DataFrame,
    inventory: pd.DataFrame,
    verified_decisions: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return review-ready row and group files without applying decisions."""

    _require_columns(
        triage,
        set(ROW_IDENTITY_COLUMNS + ROW_REVIEW_COLUMNS)
        | {
            "category_group_id",
            "review_tier",
            "suggested_manual_decision",
            "dental_title_signals",
            "nondental_title_signals",
            "category_nonprovider_signals",
            "unknown_categories",
            "automatic_final_decision_applied",
        },
        "Profile triage",
    )
    _require_columns(
        groups,
        {
            "category_group_id",
            "observed_categories",
            "observed_source_decisions",
            "category_rule_pattern",
            "review_tier",
            "suggested_manual_decision",
            "suggestion_basis",
            "profile_count",
            "markets",
            "sample_titles",
        },
        "Category groups",
    )
    _require_columns(
        inventory,
        {
            "requested_location",
            "profile_key",
            "phone",
            "domain",
            "url",
            "votes_count",
            "latitude",
            "longitude",
        },
        "Unified profile inventory",
    )
    _assert_unique(triage, "decision_id", "Profile triage")
    _assert_unique(triage, "profile_key", "Profile triage")
    _assert_unique(groups, "category_group_id", "Category groups")
    if inventory.duplicated(["requested_location", "profile_key"]).any():
        raise ValueError("Unified profile inventory contains duplicate market-profile keys")
    if triage[ROW_REVIEW_COLUMNS].apply(
        lambda column: column.map(_text).ne("").any()
    ).any():
        raise ValueError("Profile triage must have blank human decision fields")
    if triage["automatic_final_decision_applied"].astype(str).str.casefold().isin(
        {"true", "1"}
    ).any():
        raise ValueError("Profile triage unexpectedly contains automatic final decisions")

    triage_group_ids = set(triage["category_group_id"].map(_text))
    group_ids = set(groups["category_group_id"].map(_text))
    if triage_group_ids != group_ids:
        raise ValueError("Category-group identifiers do not reconcile with profile triage")
    actual_counts = triage.groupby("category_group_id").size().to_dict()
    declared_counts = {
        _text(row.category_group_id): int(row.profile_count)
        for row in groups.itertuples(index=False)
    }
    if actual_counts != declared_counts:
        raise ValueError("Category-group profile counts do not reconcile with profile triage")

    evidence = inventory.loc[
        :,
        [
            "requested_location",
            "profile_key",
            "phone",
            "domain",
            "url",
            "votes_count",
            "latitude",
            "longitude",
        ],
    ].rename(
        columns={
            "requested_location": "market",
            "phone": "source_phone",
            "domain": "source_domain",
            "url": "source_website_url",
            "votes_count": "source_votes_count",
            "latitude": "source_latitude",
            "longitude": "source_longitude",
        }
    )
    row_review = triage.merge(
        evidence,
        on=["market", "profile_key"],
        how="left",
        validate="one_to_one",
    )
    row_review = _apply_verified_decisions(row_review, verified_decisions)
    evidence_columns = [
        "source_phone",
        "source_domain",
        "source_website_url",
        "source_votes_count",
        "source_latitude",
        "source_longitude",
    ]
    if row_review[evidence_columns].isna().all(axis=1).any():
        missing = row_review.loc[
            row_review[evidence_columns].isna().all(axis=1), "decision_id"
        ].head(10)
        raise ValueError(
            "Unified inventory does not cover all triage rows; examples: "
            + ", ".join(missing)
        )
    row_review[evidence_columns] = row_review[evidence_columns].fillna("")
    row_review["direct_profile_evidence_url"] = row_review["profile_key"].map(
        _profile_evidence_url
    )
    row_review["existing_evidence_route"] = "google_profile_only"
    row_review.loc[
        row_review["source_domain"].map(_text).ne(""), "existing_evidence_route"
    ] = "domain_then_google_profile"
    row_review.loc[
        row_review["source_website_url"].map(_text).ne(""),
        "existing_evidence_route",
    ] = "website_then_google_profile"
    row_review["normalized_source_domain"] = (
        row_review["source_domain"].map(_text).str.casefold()
    )
    domain_counts = (
        row_review.loc[row_review["normalized_source_domain"].ne("")]
        .groupby(["category_group_id", "normalized_source_domain"])
        .size()
        .to_dict()
    )
    review_block_ids: list[str] = []
    review_block_bases: list[str] = []
    for row in row_review.itertuples(index=False):
        if (
            row.normalized_source_domain
            and domain_counts.get(
                (row.category_group_id, row.normalized_source_domain), 0
            )
            >= 2
        ):
            block_id = _review_block_id(
                "shared_domain", row.category_group_id, row.normalized_source_domain
            )
            basis = "shared_domain_within_category_group"
        else:
            block_id = _review_block_id("singleton", row.decision_id)
            basis = "singleton_profile"
        review_block_ids.append(block_id)
        review_block_bases.append(basis)
    row_review["review_block_id"] = review_block_ids
    row_review["review_block_basis"] = review_block_bases
    row_review["row_review_note"] = (
        "Fill this row only when it is an exception to a reviewed group decision, "
        "or when its group is marked individual_review."
    )

    group_lookup = groups.set_index("category_group_id").to_dict(orient="index")
    group_records: list[dict[str, Any]] = []
    for block_id, members in row_review.groupby("review_block_id", sort=True):
        category_group_ids = set(members["category_group_id"])
        if len(category_group_ids) != 1:
            raise ValueError("A review block spans multiple category groups")
        category_group_id = next(iter(category_group_ids))
        record = dict(group_lookup[category_group_id])
        record.update(
            {
                "review_block_id": block_id,
                "category_group_id": category_group_id,
                "review_block_basis": members["review_block_basis"].iloc[0],
                "review_domain": (
                    members["source_domain"].iloc[0]
                    if members["review_block_basis"].iloc[0]
                    == "shared_domain_within_category_group"
                    else ""
                ),
                "profile_count": len(members),
                "markets": "|".join(sorted(set(members["market"]))),
                "sample_titles": " || ".join(members["title"].head(8)),
                "profiles_with_dental_title_signal": int(
                    members["dental_title_signals"].map(_text).ne("").sum()
                ),
                "profiles_with_nondental_title_signal": int(
                    members["nondental_title_signals"].map(_text).ne("").sum()
                ),
                "profiles_with_unknown_categories": int(
                    members["unknown_categories"].map(_text).ne("").sum()
                ),
                "profiles_with_nonprovider_category_signal": int(
                    members["category_nonprovider_signals"].map(_text).ne("").sum()
                ),
                "profiles_with_existing_website": int(
                    members["source_website_url"].map(_text).ne("").sum()
                ),
                "profiles_with_phone": int(
                    members["source_phone"].map(_text).ne("").sum()
                ),
                "profiles_without_website_or_phone": int(
                    (
                        members["source_website_url"].map(_text).eq("")
                        & members["source_domain"].map(_text).eq("")
                        & members["source_phone"].map(_text).eq("")
                    ).sum()
                ),
                "allowed_group_review_actions": (
                    "individual_review|exclude_non_dentist_category|"
                    "include_dental_provider"
                ),
                "group_manual_decision": "",
                "reviewed_member_count": "",
                "group_decision_evidence": "",
                "reviewed_by": "",
                "reviewed_on": "",
            }
        )
        group_records.append(record)
    group_review = pd.DataFrame.from_records(group_records)
    if group_review["review_block_id"].duplicated().any():
        raise ValueError("Prepared review blocks are not unique")
    if int(pd.to_numeric(group_review["profile_count"]).sum()) != len(row_review):
        raise ValueError("Prepared review-block counts do not reconcile with profile rows")

    summary = {
        "analysis_status": "profile_eligibility_review_files_prepared_not_final",
        "api_requests_submitted": 0,
        "profile_rows": len(row_review),
        "category_groups": len(groups),
        "review_blocks": len(group_review),
        "shared_domain_review_blocks": int(
            group_review["review_block_basis"]
            .eq("shared_domain_within_category_group")
            .sum()
        ),
        "profiles_in_shared_domain_review_blocks": int(
            pd.to_numeric(
                group_review.loc[
                    group_review["review_block_basis"].eq(
                        "shared_domain_within_category_group"
                    ),
                    "profile_count",
                ]
            ).sum()
        ),
        "singleton_review_blocks": int(
            group_review["review_block_basis"].eq("singleton_profile").sum()
        ),
        "profiles_by_review_tier": {
            str(key): int(value)
            for key, value in row_review["review_tier"].value_counts().items()
        },
        "suggested_include_profiles": int(
            row_review["suggested_manual_decision"]
            .eq("include_dental_provider")
            .sum()
        ),
        "suggested_exclude_profiles": int(
            row_review["suggested_manual_decision"]
            .eq("exclude_non_dentist_category")
            .sum()
        ),
        "profiles_without_safe_suggestion": int(
            row_review["suggested_manual_decision"].map(_text).eq("").sum()
        ),
        "profiles_with_existing_website": int(
            row_review["source_website_url"].map(_text).ne("").sum()
        ),
        "profiles_with_phone": int(
            row_review["source_phone"].map(_text).ne("").sum()
        ),
        "profiles_with_website_or_phone": int(
            (
                row_review["source_website_url"].map(_text).ne("")
                | row_review["source_domain"].map(_text).ne("")
                | row_review["source_phone"].map(_text).ne("")
            ).sum()
        ),
        "profiles_without_website_or_phone": int(
            (
                row_review["source_website_url"].map(_text).eq("")
                & row_review["source_domain"].map(_text).eq("")
                & row_review["source_phone"].map(_text).eq("")
            ).sum()
        ),
        "automatic_final_decisions_applied": 0,
        "verified_profile_decisions_prefilled": int(
            row_review["verified_decision_applied"].sum()
        ),
        "next_required_action": (
            "Review every member of any block given a block decision. Mark heterogeneous "
            "blocks individual_review and fill their row decisions. Suggestions are not decisions."
        ),
    }
    return row_review, group_review, summary


def apply_profile_eligibility_review(
    blank_decisions: pd.DataFrame,
    reviewed_rows: pd.DataFrame,
    reviewed_groups: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Expand reviewed group decisions and row exceptions into a complete 46a file."""

    _require_columns(
        blank_decisions,
        set(ROW_IDENTITY_COLUMNS + ROW_REVIEW_COLUMNS),
        "Blank 46a decisions",
    )
    _require_columns(
        reviewed_rows,
        set(ROW_IDENTITY_COLUMNS + ROW_REVIEW_COLUMNS)
        | {"category_group_id", "review_block_id"},
        "Reviewed rows",
    )
    _require_columns(
        reviewed_groups,
        {
            "review_block_id",
            "category_group_id",
            "profile_count",
            "group_manual_decision",
            "reviewed_member_count",
            "group_decision_evidence",
            "reviewed_by",
            "reviewed_on",
        },
        "Reviewed groups",
    )
    for frame, label in [
        (blank_decisions, "Blank 46a decisions"),
        (reviewed_rows, "Reviewed rows"),
    ]:
        _assert_unique(frame, "decision_id", label)
        _assert_unique(frame, "profile_key", label)
    _assert_unique(reviewed_groups, "review_block_id", "Reviewed groups")
    if blank_decisions[ROW_REVIEW_COLUMNS].apply(
        lambda column: column.map(_text).ne("").any()
    ).any():
        raise ValueError("46a input must be the unmodified blank decision file")

    if set(blank_decisions["decision_id"]) != set(reviewed_rows["decision_id"]):
        raise ValueError("Reviewed rows do not exactly cover the frozen 46a template")
    blank_identity = (
        blank_decisions[ROW_IDENTITY_COLUMNS].fillna("").astype(str).reset_index(drop=True)
    )
    reviewed_identity = (
        reviewed_rows.set_index("decision_id")
        .loc[blank_decisions["decision_id"]]
        .reset_index()
        .loc[:, ROW_IDENTITY_COLUMNS]
        .fillna("")
        .astype(str)
        .reset_index(drop=True)
    )
    if not blank_identity.equals(reviewed_identity):
        raise ValueError("Reviewed row identity fields differ from the frozen 46a template")

    group_lookup: dict[str, dict[str, str]] = {}
    for row in reviewed_groups.itertuples(index=False):
        group_id = _text(row.review_block_id)
        action = _text(row.group_manual_decision)
        if action and action not in GROUP_REVIEW_ACTIONS:
            raise ValueError(f"Invalid group action for {group_id}: {action}")
        if action in ALLOWED_FINAL_DECISIONS:
            try:
                reviewed_count = int(_text(row.reviewed_member_count))
            except ValueError as exc:
                raise ValueError(
                    f"Group {group_id} must record an integer reviewed_member_count"
                ) from exc
            if reviewed_count != int(row.profile_count):
                raise ValueError(
                    f"Group {group_id} reviewed_member_count must equal profile_count"
                )
            for field in ["group_decision_evidence", "reviewed_by", "reviewed_on"]:
                if not _text(getattr(row, field)):
                    raise ValueError(f"Group {group_id} is missing {field}")
        group_lookup[group_id] = {
            "action": action,
            "evidence": _text(row.group_decision_evidence),
            "reviewed_by": _text(row.reviewed_by),
            "reviewed_on": _text(row.reviewed_on),
        }

    completed_records: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for row in reviewed_rows.itertuples(index=False):
        record = row._asdict()
        row_decision = _text(record.get("manual_decision"))
        group_id = _text(record.get("review_block_id"))
        group = group_lookup.get(group_id)
        if group is None:
            raise ValueError(f"Missing reviewed group for {group_id}")

        if row_decision:
            if row_decision not in ALLOWED_FINAL_DECISIONS:
                raise ValueError(
                    f"Invalid row decision for {record['decision_id']}: {row_decision}"
                )
            for field in ["decision_evidence", "reviewed_by", "reviewed_on"]:
                if not _text(record.get(field)):
                    raise ValueError(f"Row {record['decision_id']} is missing {field}")
            evidence_url = _text(record.get("evidence_url")) or _profile_evidence_url(
                record.get("profile_key")
            )
            decision_source = "individual_row"
            evidence = _text(record.get("decision_evidence"))
            reviewed_by = _text(record.get("reviewed_by"))
            reviewed_on = _text(record.get("reviewed_on"))
        elif group["action"] in ALLOWED_FINAL_DECISIONS:
            row_decision = group["action"]
            evidence_url = _profile_evidence_url(record.get("profile_key"))
            decision_source = "reviewed_group"
            evidence = group["evidence"]
            reviewed_by = group["reviewed_by"]
            reviewed_on = group["reviewed_on"]
        else:
            unresolved.append(_text(record.get("decision_id")))
            continue

        allowed = set(_text(record.get("allowed_manual_decisions")).split("|"))
        if row_decision not in allowed:
            raise ValueError(
                f"Decision {row_decision} is not allowed for {record['decision_id']}"
            )
        completed = {
            column: record[column]
            for column in blank_decisions.columns
            if column not in ROW_REVIEW_COLUMNS
        }
        completed.update(
            {
                "manual_decision": row_decision,
                "decision_evidence": evidence,
                "evidence_url": evidence_url,
                "reviewed_by": reviewed_by,
                "reviewed_on": reviewed_on,
            }
        )
        completed_records.append(completed)
        audit_records.append(
            {
                "decision_id": record["decision_id"],
                "market": record["market"],
                "profile_key": record["profile_key"],
                "title": record["title"],
                "category_group_id": record["category_group_id"],
                "review_block_id": group_id,
                "manual_decision": row_decision,
                "decision_source": decision_source,
                "evidence_url": evidence_url,
            }
        )

    if unresolved:
        sample = ", ".join(unresolved[:10])
        raise ValueError(
            f"Profile eligibility review is incomplete for {len(unresolved)} rows; "
            f"examples: {sample}"
        )
    completed = pd.DataFrame.from_records(completed_records)
    completed = completed.loc[:, blank_decisions.columns]
    audit = pd.DataFrame.from_records(audit_records)
    if len(completed) != len(blank_decisions):
        raise ValueError("Completed profile decisions do not preserve the frozen row count")

    summary = {
        "analysis_status": "profile_eligibility_review_complete_ready_for_46a",
        "api_requests_submitted": 0,
        "completed_profile_decisions": len(completed),
        "individual_row_decisions": int(
            audit["decision_source"].eq("individual_row").sum()
        ),
        "reviewed_group_decisions": int(
            audit["decision_source"].eq("reviewed_group").sum()
        ),
        "included_profiles": int(
            audit["manual_decision"].eq("include_dental_provider").sum()
        ),
        "excluded_profiles": int(
            audit["manual_decision"].eq("exclude_non_dentist_category").sum()
        ),
        "remaining_unresolved": 0,
        "automatic_final_decisions_applied": 0,
        "next_required_action": (
            "Pass the completed decision file to stage 46a and review its location pairs, "
            "blocks, and triage outputs."
        ),
    }
    return completed, audit, summary
