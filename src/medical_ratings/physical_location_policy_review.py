"""Prepare one frozen policy-review queue for provisional physical locations."""

from __future__ import annotations

from typing import Any

import pandas as pd


TRIAGE_REQUIRED = {
    "physical_location_group",
    "mapped_location",
    "profile_count",
    "base_address_count",
    "review_tier",
    "review_reason",
    "manual_decision",
}
PROFILE_REQUIRED = {
    "physical_location_group",
    "clinic_key",
    "title",
    "address",
    "phone",
    "domain",
    "profile_role",
    "review_tier",
}


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        result[column] = result[column].fillna("").astype(str).str.strip()
    return result


def _require(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def prepare_physical_location_policy_review(
    block_triage: pd.DataFrame,
    block_profiles: pd.DataFrame,
    *,
    expected_blocks: int = 5_679,
    expected_profiles: int = 15_796,
    expected_routine: int = 4_031,
    expected_focused: int = 192,
    expected_complex: int = 1_456,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Validate stage 46m outputs and prepare one consolidated review queue."""

    _require(block_triage, TRIAGE_REQUIRED, "physical-location block triage")
    _require(block_profiles, PROFILE_REQUIRED, "physical-location block profiles")
    triage = _clean(block_triage)
    profiles = _clean(block_profiles)
    if triage["physical_location_group"].duplicated().any():
        raise ValueError("Physical-location triage contains duplicate block IDs")
    if profiles["clinic_key"].duplicated().any():
        raise ValueError("Physical-location block profiles contain duplicate clinic keys")
    if len(triage) != expected_blocks:
        raise ValueError(f"Triage has {len(triage)} blocks; expected {expected_blocks}")
    if len(profiles) != expected_profiles:
        raise ValueError(
            f"Block profiles contain {len(profiles)} rows; expected {expected_profiles}"
        )
    if not triage["manual_decision"].eq("pending_manual_review").all():
        raise ValueError("Triage contains decisions outside the untouched pending baseline")

    for column in ("profile_count", "base_address_count"):
        triage[column] = pd.to_numeric(triage[column], errors="raise").astype(int)
    tiers = triage["review_tier"].value_counts()
    expected_tiers = {
        "routine_shared_identity": expected_routine,
        "focused_review": expected_focused,
        "complex_review": expected_complex,
    }
    observed_tiers = {tier: int(tiers.get(tier, 0)) for tier in expected_tiers}
    if observed_tiers != expected_tiers or int(tiers.sum()) != expected_blocks:
        raise ValueError(
            f"Review-tier counts changed; observed={observed_tiers}, "
            f"expected={expected_tiers}"
        )

    profile_counts = profiles.groupby("physical_location_group").size()
    if set(profile_counts.index) != set(triage["physical_location_group"]):
        raise ValueError("Block-profile coverage differs from the triage block set")
    expected_sizes = triage.set_index("physical_location_group")["profile_count"]
    mismatched = profile_counts.ne(expected_sizes.reindex(profile_counts.index))
    if mismatched.any():
        raise ValueError(
            "Block-profile counts differ from triage for blocks: "
            f"{profile_counts.index[mismatched].tolist()[:10]}"
        )

    routine = triage["review_tier"].eq("routine_shared_identity")
    multi_address = triage["review_tier"].eq("complex_review") & triage[
        "base_address_count"
    ].gt(1)
    triage["suggested_policy_decision"] = "manual_review_required"
    triage.loc[routine, "suggested_policy_decision"] = (
        "merge_current_block_as_one_physical_location"
    )
    triage.loc[multi_address, "suggested_policy_decision"] = (
        "split_block_by_normalized_base_address"
    )
    triage["policy_basis"] = ""
    triage.loc[routine, "policy_basis"] = (
        "one normalized base address, shared phone or domain, maximum coordinate "
        "spread at most 50 meters, and strong-edge density at least 0.80"
    )
    triage.loc[multi_address, "policy_basis"] = (
        "a physical location cannot span multiple normalized base addresses "
        "without a documented campus exception"
    )
    triage.loc[~(routine | multi_address), "policy_basis"] = (
        "identity evidence is incomplete, mixed, or requires a campus exception"
    )
    triage["allowed_manual_decisions"] = (
        "merge_current_block_as_one_physical_location|"
        "split_block_by_normalized_base_address|"
        "keep_each_profile_as_separate_location|custom_partition"
    )
    for column in (
        "manual_policy_decision",
        "custom_partition_json",
        "decision_evidence",
        "reviewed_by",
        "reviewed_on",
    ):
        triage[column] = ""

    manual_groups = set(
        triage.loc[
            triage["suggested_policy_decision"].eq("manual_review_required"),
            "physical_location_group",
        ]
    )
    manual_queue = triage.loc[
        triage["physical_location_group"].isin(manual_groups)
    ].copy()
    manual_profiles = profiles.loc[
        profiles["physical_location_group"].isin(manual_groups)
    ].copy()
    tier_order = {"complex_review": 0, "focused_review": 1}
    manual_queue["_tier_order"] = manual_queue["review_tier"].map(tier_order)
    manual_queue = manual_queue.sort_values(
        ["_tier_order", "profile_count", "mapped_location", "physical_location_group"],
        ascending=[True, False, True, True],
        ignore_index=True,
    ).drop(columns="_tier_order")
    manual_profiles["_tier_order"] = manual_profiles["review_tier"].map(tier_order)
    manual_profiles = manual_profiles.sort_values(
        ["_tier_order", "physical_location_group", "profile_role", "title", "clinic_key"],
        ignore_index=True,
    ).drop(columns="_tier_order")
    decisions = triage.sort_values(
        ["mapped_location", "physical_location_group"], ignore_index=True
    )
    summary = {
        "analysis_status": "physical_location_policy_review_prepared_not_applied",
        "api_requests_submitted": 0,
        "provisional_multi_profile_blocks": int(len(decisions)),
        "profiles_in_multi_profile_blocks": int(len(profiles)),
        "suggested_merge_current_block": int(routine.sum()),
        "suggested_split_by_base_address": int(multi_address.sum()),
        "manual_review_blocks": int(len(manual_queue)),
        "manual_review_profiles": int(len(manual_profiles)),
        "automatic_profile_or_location_merges": 0,
        "final_competition_location_ids_assigned": 0,
        "regression_balltree_modified": False,
        "decision_boundary": (
            "Suggested policy decisions are not final decisions. Application requires "
            "a separate complete reviewed decision file with evidence and reviewer metadata."
        ),
    }
    return {
        "policy_decisions": decisions,
        "manual_review_queue": manual_queue,
        "manual_review_profiles": manual_profiles,
    }, summary
