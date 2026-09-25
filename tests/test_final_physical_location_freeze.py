from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.final_physical_location_freeze import (
    freeze_physical_competition_locations,
)


def _row(key: str, group: str, size: int, address: str) -> dict[str, object]:
    return {
        "clinic_key": key,
        "profile_key": f"profile:{key}",
        "cid": key,
        "physical_location_group": group,
        "location_group_size": size,
        "mapped_location": "Market",
        "title": f"Clinic {key}",
        "address": address,
        "votes_count": "10",
        "observation_count": "1",
        "profile_role": "organization",
        "outcome_profile_included": "True",
    }


def _blocks() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _row("s1", "singleton", 1, "1 Main St"),
            _row("r1", "routine", 2, "2 Main St"),
            _row("r2", "routine", 2, "2 Main St, Suite 1"),
            _row("m1", "multi", 3, "3 Main St"),
            _row("m2", "multi", 3, "3 Main St, Suite 2"),
            _row("m3", "multi", 3, "4 Main St"),
            _row("u1", "unresolved", 2, "5 Main St"),
            _row("u2", "unresolved", 2, "5 Main St, Suite 5"),
        ]
    )


def _policy() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "physical_location_group": "routine",
                "profile_count": "2",
                "base_address_count": "1",
                "review_tier": "routine_shared_identity",
                "suggested_policy_decision": (
                    "merge_current_block_as_one_physical_location"
                ),
            },
            {
                "physical_location_group": "multi",
                "profile_count": "3",
                "base_address_count": "2",
                "review_tier": "complex_review",
                "suggested_policy_decision": (
                    "split_block_by_normalized_base_address"
                ),
            },
            {
                "physical_location_group": "unresolved",
                "profile_count": "2",
                "base_address_count": "1",
                "review_tier": "focused_review",
                "suggested_policy_decision": "manual_review_required",
            },
        ]
    )


def _freeze(blocks: pd.DataFrame | None = None, policy: pd.DataFrame | None = None):
    return freeze_physical_competition_locations(
        _blocks() if blocks is None else blocks,
        _policy() if policy is None else policy,
        expected_candidate_rows=8,
        expected_provisional_blocks=4,
        expected_multi_profile_blocks=3,
        expected_outcome_profiles=8,
        expected_main_locations=6,
        expected_sensitivity_locations=5,
    )


def test_freezes_conservative_main_and_address_merge_sensitivity() -> None:
    frames, summary = _freeze()
    crosswalk = frames["crosswalk"].set_index("clinic_key")

    assert crosswalk.loc["r1", "competition_location_id"] == crosswalk.loc[
        "r2", "competition_location_id"
    ]
    assert crosswalk.loc["m1", "competition_location_id"] == crosswalk.loc[
        "m2", "competition_location_id"
    ]
    assert crosswalk.loc["m1", "competition_location_id"] != crosswalk.loc[
        "m3", "competition_location_id"
    ]
    assert crosswalk.loc["u1", "competition_location_id"] != crosswalk.loc[
        "u2", "competition_location_id"
    ]
    assert crosswalk.loc[
        "u1", "address_merge_sensitivity_location_id"
    ] == crosswalk.loc["u2", "address_merge_sensitivity_location_id"]
    assert summary["remaining_manual_location_reviews"] == 0
    assert summary["profile_identities_merged"] == 0


def test_rejects_policy_that_does_not_cover_every_multi_profile_block() -> None:
    with pytest.raises(ValueError, match="expected 3"):
        _freeze(policy=_policy().iloc[:-1].copy())


def test_rejects_duplicate_candidate_keys() -> None:
    blocks = _blocks()
    blocks.loc[1, "clinic_key"] = "s1"
    with pytest.raises(ValueError, match="unique nonblank"):
        _freeze(blocks=blocks)


def test_location_ids_are_stable_under_input_reordering() -> None:
    first, _ = _freeze()
    second, _ = _freeze(blocks=_blocks().sample(frac=1, random_state=7))
    left = first["crosswalk"].set_index("clinic_key")["competition_location_id"]
    right = second["crosswalk"].set_index("clinic_key")["competition_location_id"]
    assert left.sort_index().equals(right.sort_index())
