"""Resolve Business Listings profiles into competition locations without merging outcomes."""

from __future__ import annotations

from typing import Any

import pandas as pd


REQUIRED_BLOCK_COLUMNS = {
    "clinic_key",
    "physical_location_group",
    "location_group_size",
    "outcome_profile_included",
    "suggested_canonical_profile",
}
REQUIRED_TRIAGE_COLUMNS = {
    "physical_location_group",
    "review_tier",
}
REQUIRED_DECISION_COLUMNS = {
    "physical_location_group",
    "competition_location_action",
    "canonical_competition_clinic_key",
    "evidence_basis",
    "evidence_url",
    "decision_note",
}
ALLOWED_ACTIONS = {"accept_one_location", "exclude_block"}


def _boolean(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no", "", "nan"}:
            return False
        raise ValueError(f"Cannot interpret boolean value: {value}")
    if value is None or pd.isna(value):
        return False
    return bool(value)


def resolve_competition_locations(
    blocks: pd.DataFrame,
    triage: pd.DataFrame,
    decisions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Resolve singleton, routine, and reviewed blocks while preserving outcome identities."""

    missing_blocks = REQUIRED_BLOCK_COLUMNS - set(blocks.columns)
    if missing_blocks:
        raise KeyError(f"Location blocks are missing columns: {sorted(missing_blocks)}")
    missing_triage = REQUIRED_TRIAGE_COLUMNS - set(triage.columns)
    if missing_triage:
        raise KeyError(f"Location triage is missing columns: {sorted(missing_triage)}")
    missing_decisions = REQUIRED_DECISION_COLUMNS - set(decisions.columns)
    if missing_decisions:
        raise KeyError(f"Location decisions are missing columns: {sorted(missing_decisions)}")
    if blocks["clinic_key"].isna().any() or blocks["clinic_key"].duplicated().any():
        raise ValueError("Location blocks require unique nonblank clinic_key values")
    if triage["physical_location_group"].duplicated().any():
        raise ValueError("Location triage requires one row per physical_location_group")
    if decisions["physical_location_group"].duplicated().any():
        raise ValueError("Location decisions require one row per physical_location_group")
    invalid_actions = set(decisions["competition_location_action"].dropna()) - ALLOWED_ACTIONS
    if invalid_actions:
        raise ValueError(f"Unsupported competition location actions: {sorted(invalid_actions)}")

    multi = blocks.loc[blocks["location_group_size"].gt(1)].copy()
    multi_groups = set(multi["physical_location_group"].astype(str))
    triage_groups = set(triage["physical_location_group"].astype(str))
    if multi_groups != triage_groups:
        raise ValueError("Triage groups must exactly match multi-profile location blocks")

    decision_map = decisions.set_index("physical_location_group", drop=False)
    triage_map = triage.set_index("physical_location_group", drop=False)
    records: list[dict[str, Any]] = []
    unresolved_groups: list[str] = []

    for _, row in blocks.iterrows():
        group_id = str(row["physical_location_group"])
        size = int(row["location_group_size"])
        evidence_basis = ""
        evidence_url = ""
        decision_note = ""
        if size == 1:
            action = "accept_one_location"
            source = "singleton_no_consolidation"
            canonical_key = str(row["clinic_key"])
        else:
            tier = str(triage_map.loc[group_id, "review_tier"])
            if tier == "routine_shared_identity":
                action = "accept_one_location"
                source = "frozen_routine_shared_identity_rule"
                canonical_rows = blocks.loc[
                    blocks["physical_location_group"].astype(str).eq(group_id)
                    & blocks["suggested_canonical_profile"].map(_boolean)
                ]
                canonical_key = (
                    str(canonical_rows.iloc[0]["clinic_key"])
                    if not canonical_rows.empty
                    else str(row["clinic_key"])
                )
                evidence_basis = "triage_rule"
                decision_note = (
                    "One base address, at most 50m spread, dense strong-evidence graph, "
                    "and a shared phone or domain."
                )
            elif group_id in decision_map.index:
                decision = decision_map.loc[group_id]
                action = str(decision["competition_location_action"])
                source = "reviewed_complex_or_focused_block"
                canonical_key = str(decision["canonical_competition_clinic_key"])
                evidence_basis = str(decision["evidence_basis"])
                evidence_url = "" if pd.isna(decision["evidence_url"]) else str(decision["evidence_url"])
                decision_note = str(decision["decision_note"])
                group_keys = set(
                    blocks.loc[
                        blocks["physical_location_group"].astype(str).eq(group_id),
                        "clinic_key",
                    ].astype(str)
                )
                if action == "accept_one_location" and canonical_key not in group_keys:
                    raise ValueError(f"Canonical key is outside block {group_id}: {canonical_key}")
            else:
                action = "pending_manual_review"
                source = "unresolved_complex_or_focused_block"
                canonical_key = ""
                unresolved_groups.append(group_id)

        included = action == "accept_one_location"
        records.append(
            {
                "clinic_key": str(row["clinic_key"]),
                "physical_location_group": group_id,
                "competition_location_id": group_id if included else "",
                "competition_location_included": included,
                "competition_location_action": action,
                "canonical_competition_clinic_key": canonical_key,
                "is_canonical_competition_profile": str(row["clinic_key"]) == canonical_key,
                "resolution_source": source,
                "evidence_basis": evidence_basis,
                "evidence_url": evidence_url,
                "decision_note": decision_note,
            }
        )

    crosswalk = pd.DataFrame.from_records(records)
    outcome = blocks[["clinic_key", "physical_location_group", "outcome_profile_included"]].copy()
    outcome["outcome_profile_included"] = outcome["outcome_profile_included"].map(_boolean)
    outcome["outcome_entity_id"] = outcome["clinic_key"].astype(str)
    outcome["outcome_identity_action"] = "retain_profile_identity_no_rating_merge"
    outcome = outcome.sort_values(["physical_location_group", "clinic_key"]).reset_index(drop=True)

    unresolved = triage.loc[
        triage["physical_location_group"].astype(str).isin(set(unresolved_groups))
    ].copy()
    included_crosswalk = crosswalk.loc[crosswalk["competition_location_included"]]
    summary = {
        "analysis_status": (
            "pilot_location_resolution_complete"
            if unresolved.empty
            else "pilot_location_resolution_incomplete"
        ),
        "api_requests_submitted": 0,
        "input_competition_profiles": len(blocks),
        "input_review_blocks": int(blocks["physical_location_group"].nunique()),
        "singleton_locations_accepted": int(
            blocks.loc[blocks["location_group_size"].eq(1), "physical_location_group"].nunique()
        ),
        "routine_blocks_accepted_by_frozen_rule": int(
            triage["review_tier"].eq("routine_shared_identity").sum()
        ),
        "complex_or_focused_blocks_accepted_by_review": int(
            included_crosswalk.loc[
                included_crosswalk["resolution_source"].eq("reviewed_complex_or_focused_block"),
                "physical_location_group",
            ].nunique()
        ),
        "unresolved_blocks": int(len(unresolved)),
        "resolved_competition_locations": int(
            included_crosswalk["competition_location_id"].nunique()
        ),
        "profiles_consolidated_for_competition_count": int(
            len(included_crosswalk)
            - included_crosswalk["competition_location_id"].nunique()
        ),
        "outcome_profiles_retained_with_separate_identity": int(
            outcome["outcome_profile_included"].sum()
        ),
        "outcome_rating_merges_performed": 0,
        "legacy_carry_forward_locations_added": 0,
        "interpretation_limit": (
            "Competition profiles may share one location ID, but rating histories remain "
            "separate profile outcomes. The validated legacy carry-forward is added later."
        ),
    }
    return crosswalk, outcome, unresolved, summary
