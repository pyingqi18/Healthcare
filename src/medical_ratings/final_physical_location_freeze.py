"""Freeze main and sensitivity physical competition locations without more review."""

from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from medical_ratings.business_listings_location_triage import _base_address


BLOCK_REQUIRED = {
    "clinic_key",
    "profile_key",
    "physical_location_group",
    "location_group_size",
    "mapped_location",
    "title",
    "address",
    "votes_count",
    "observation_count",
    "profile_role",
    "outcome_profile_included",
}
POLICY_REQUIRED = {
    "physical_location_group",
    "profile_count",
    "base_address_count",
    "review_tier",
    "suggested_policy_decision",
}
POLICY_DECISIONS = {
    "merge_current_block_as_one_physical_location",
    "split_block_by_normalized_base_address",
    "manual_review_required",
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


def _boolean(value: Any) -> bool:
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no", "", "nan"}:
        return False
    raise ValueError(f"Cannot interpret boolean value: {value}")


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return -1.0
    return -1.0 if pd.isna(number) else number


def _location_id(keys: list[str]) -> str:
    payload = "|".join(sorted(keys))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"competition_location:{digest}"


def _assign_location_ids(frame: pd.DataFrame, token_column: str) -> pd.Series:
    identifiers: dict[str, str] = {}
    for token, group in frame.groupby(token_column, sort=True):
        identifiers[str(token)] = _location_id(group["clinic_key"].astype(str).tolist())
    return frame[token_column].map(identifiers)


def _choose_canonical(group: pd.DataFrame) -> pd.Series:
    ranked = group.copy()
    ranked["_role"] = ranked["profile_role"].eq("organization").astype(int)
    ranked["_votes"] = ranked["votes_count"].map(_number)
    ranked["_observations"] = ranked["observation_count"].map(_number)
    ranked["_complete"] = ranked[["title", "address"]].ne("").sum(axis=1)
    ranked = ranked.sort_values(
        ["_role", "_votes", "_observations", "_complete", "clinic_key"],
        ascending=[False, False, False, False, True],
        kind="stable",
    )
    return ranked.iloc[0]


def _build_locations(
    crosswalk: pd.DataFrame,
    *,
    id_column: str,
    rule_column: str,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for location_id, group in crosswalk.groupby(id_column, sort=True):
        canonical = _choose_canonical(group)
        rules = sorted(set(group[rule_column]))
        if len(rules) != 1:
            raise AssertionError(
                f"Competition location {location_id} contains mixed resolution rules"
            )
        records.append(
            {
                "competition_location_id": location_id,
                "mapped_location": canonical["mapped_location"],
                "canonical_clinic_key": canonical["clinic_key"],
                "canonical_profile_key": canonical["profile_key"],
                "canonical_title": canonical["title"],
                "canonical_address": canonical["address"],
                "member_candidate_count": int(len(group)),
                "outcome_profile_count": int(
                    group["outcome_profile_included"].map(_boolean).sum()
                ),
                "resolution_rule": rules[0],
                "member_clinic_keys": "|".join(sorted(group["clinic_key"])),
            }
        )
    return pd.DataFrame.from_records(records).sort_values(
        ["mapped_location", "canonical_title", "canonical_address", "competition_location_id"],
        kind="stable",
        ignore_index=True,
    )


def freeze_physical_competition_locations(
    location_blocks: pd.DataFrame,
    policy_decisions: pd.DataFrame,
    *,
    expected_candidate_rows: int = 29_677,
    expected_provisional_blocks: int = 19_560,
    expected_multi_profile_blocks: int = 5_679,
    expected_outcome_profiles: int = 29_550,
    expected_main_locations: int | None = 22_299,
    expected_sensitivity_locations: int | None = 20_762,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Apply a conservative main rule and an address-merge sensitivity rule."""

    _require(location_blocks, BLOCK_REQUIRED, "physical-location review blocks")
    _require(policy_decisions, POLICY_REQUIRED, "physical-location policy decisions")
    blocks = _clean(location_blocks)
    policy = _clean(policy_decisions)
    if blocks["clinic_key"].duplicated().any() or blocks["clinic_key"].eq("").any():
        raise ValueError("Location blocks require unique nonblank clinic keys")
    if policy["physical_location_group"].duplicated().any():
        raise ValueError("Policy decisions contain duplicate block IDs")
    if len(blocks) != expected_candidate_rows:
        raise ValueError(
            f"Location blocks contain {len(blocks)} rows; expected {expected_candidate_rows}"
        )
    if blocks["physical_location_group"].nunique() != expected_provisional_blocks:
        raise ValueError("Provisional location block count changed")
    if len(policy) != expected_multi_profile_blocks:
        raise ValueError(
            f"Policy table contains {len(policy)} rows; expected {expected_multi_profile_blocks}"
        )
    invalid = sorted(set(policy["suggested_policy_decision"]) - POLICY_DECISIONS)
    if invalid:
        raise ValueError(f"Policy table contains unsupported suggestions: {invalid}")

    sizes = blocks.groupby("physical_location_group").size()
    multi_ids = set(sizes.loc[sizes.gt(1)].index)
    if multi_ids != set(policy["physical_location_group"]):
        raise ValueError("Policy table does not exactly cover the multi-profile blocks")
    policy_sizes = pd.to_numeric(
        policy.set_index("physical_location_group")["profile_count"], errors="raise"
    ).astype(int)
    if not sizes.loc[policy_sizes.index].equals(policy_sizes):
        raise ValueError("Policy profile counts differ from location-block membership")
    outcome_count = int(blocks["outcome_profile_included"].map(_boolean).sum())
    if outcome_count != expected_outcome_profiles:
        raise ValueError(
            f"Outcome profile count is {outcome_count}; expected {expected_outcome_profiles}"
        )

    suggestion = policy.set_index("physical_location_group")[
        "suggested_policy_decision"
    ].to_dict()
    blocks["normalized_base_address"] = blocks["address"].map(
        lambda value: _base_address(value) or ""
    )
    main_tokens: list[str] = []
    main_rules: list[str] = []
    sensitivity_tokens: list[str] = []
    sensitivity_rules: list[str] = []
    for row in blocks.itertuples(index=False):
        group_id = str(row.physical_location_group)
        decision = suggestion.get(group_id)
        if decision is None:
            main_tokens.append(f"singleton:{row.clinic_key}")
            main_rules.append("singleton_exact_profile_or_legacy_anchor")
            sensitivity_tokens.append(f"singleton:{row.clinic_key}")
            sensitivity_rules.append("singleton_exact_profile_or_legacy_anchor")
        elif decision == "merge_current_block_as_one_physical_location":
            main_tokens.append(f"accepted_block:{group_id}")
            main_rules.append("routine_shared_identity_block")
            sensitivity_tokens.append(f"accepted_block:{group_id}")
            sensitivity_rules.append("routine_shared_identity_block")
        elif decision == "split_block_by_normalized_base_address":
            base = str(row.normalized_base_address)
            if not base:
                base = f"missing_address:{row.clinic_key}"
            main_tokens.append(f"base_address:{group_id}:{base}")
            main_rules.append("split_provisional_block_by_normalized_base_address")
            sensitivity_tokens.append(f"base_address:{group_id}:{base}")
            sensitivity_rules.append(
                "split_provisional_block_by_normalized_base_address"
            )
        elif decision == "manual_review_required":
            main_tokens.append(f"conservative_profile:{row.clinic_key}")
            main_rules.append("conservative_keep_exact_profile_separate")
            sensitivity_tokens.append(f"address_merge_block:{group_id}")
            sensitivity_rules.append("address_merge_sensitivity_current_block")
        else:
            raise AssertionError(f"Unhandled policy decision: {decision}")

    blocks["_main_token"] = main_tokens
    blocks["competition_location_resolution_rule"] = main_rules
    blocks["_sensitivity_token"] = sensitivity_tokens
    blocks["address_merge_sensitivity_resolution_rule"] = sensitivity_rules
    blocks["competition_location_id"] = _assign_location_ids(blocks, "_main_token")
    blocks["address_merge_sensitivity_location_id"] = _assign_location_ids(
        blocks, "_sensitivity_token"
    )
    crosswalk_columns = [
        "clinic_key",
        "profile_key",
        "cid",
        "mapped_location",
        "title",
        "address",
        "votes_count",
        "observation_count",
        "profile_role",
        "outcome_profile_included",
        "physical_location_group",
        "competition_location_id",
        "competition_location_resolution_rule",
        "address_merge_sensitivity_location_id",
        "address_merge_sensitivity_resolution_rule",
    ]
    crosswalk = blocks[crosswalk_columns].sort_values(
        ["mapped_location", "competition_location_id", "title", "clinic_key"],
        kind="stable",
        ignore_index=True,
    )
    main_locations = _build_locations(
        crosswalk,
        id_column="competition_location_id",
        rule_column="competition_location_resolution_rule",
    )
    sensitivity_locations = _build_locations(
        crosswalk,
        id_column="address_merge_sensitivity_location_id",
        rule_column="address_merge_sensitivity_resolution_rule",
    )
    sensitivity_locations = sensitivity_locations.rename(
        columns={"competition_location_id": "address_merge_sensitivity_location_id"}
    )
    if expected_main_locations is not None and len(main_locations) != expected_main_locations:
        raise ValueError(
            f"Main location count is {len(main_locations)}; expected {expected_main_locations}"
        )
    if (
        expected_sensitivity_locations is not None
        and len(sensitivity_locations) != expected_sensitivity_locations
    ):
        raise ValueError(
            "Address-merge sensitivity location count is "
            f"{len(sensitivity_locations)}; expected {expected_sensitivity_locations}"
        )
    summary = {
        "analysis_status": "physical_competition_locations_frozen",
        "api_requests_submitted": 0,
        "location_candidate_rows": int(len(blocks)),
        "outcome_profiles_preserved": outcome_count,
        "provisional_location_blocks": int(sizes.size),
        "multi_profile_policy_blocks": int(len(policy)),
        "final_main_competition_locations": int(len(main_locations)),
        "address_merge_sensitivity_locations": int(len(sensitivity_locations)),
        "main_candidate_reduction_from_grouping": int(len(blocks) - len(main_locations)),
        "sensitivity_candidate_reduction_from_grouping": int(
            len(blocks) - len(sensitivity_locations)
        ),
        "remaining_manual_location_reviews": 0,
        "profile_identities_merged": 0,
        "regression_balltree_modified": False,
        "main_rule": (
            "Accept routine shared-identity blocks, split multi-address blocks by "
            "normalized base address, and keep unresolved same-address profiles separate."
        ),
        "sensitivity_rule": (
            "Use the main rule except that unresolved same-address provisional blocks "
            "are grouped as one competition location."
        ),
    }
    return {
        "crosswalk": crosswalk.drop(columns=["votes_count", "observation_count"]),
        "main_locations": main_locations,
        "sensitivity_locations": sensitivity_locations,
    }, summary
