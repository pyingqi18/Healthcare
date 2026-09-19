from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.business_listings_location_resolution import resolve_competition_locations


def block(key: str, group: str, size: int, canonical: bool = False) -> dict[str, object]:
    return {
        "clinic_key": key,
        "physical_location_group": group,
        "location_group_size": size,
        "outcome_profile_included": True,
        "suggested_canonical_profile": canonical,
    }


def decision(group: str, canonical: str) -> dict[str, str]:
    return {
        "physical_location_group": group,
        "competition_location_action": "accept_one_location",
        "canonical_competition_clinic_key": canonical,
        "evidence_basis": "manual_evidence",
        "evidence_url": "https://example.org",
        "decision_note": "same practice location",
    }


def test_resolution_separates_competition_locations_from_outcome_profiles() -> None:
    blocks = pd.DataFrame([
        block("solo", "g0", 1, True),
        block("org", "g1", 2, True),
        block("doctor", "g1", 2),
        block("reviewed-org", "g2", 2, True),
        block("reviewed-doctor", "g2", 2),
    ])
    triage = pd.DataFrame([
        {"physical_location_group": "g1", "review_tier": "routine_shared_identity"},
        {"physical_location_group": "g2", "review_tier": "complex_review"},
    ])
    decisions = pd.DataFrame([decision("g2", "reviewed-org")])
    crosswalk, outcomes, unresolved, summary = resolve_competition_locations(
        blocks, triage, decisions
    )
    assert crosswalk["competition_location_id"].nunique() == 3
    assert outcomes["outcome_entity_id"].nunique() == 5
    assert outcomes["outcome_identity_action"].eq(
        "retain_profile_identity_no_rating_merge"
    ).all()
    assert unresolved.empty
    assert summary["profiles_consolidated_for_competition_count"] == 2
    assert summary["outcome_rating_merges_performed"] == 0


def test_resolution_leaves_unreviewed_complex_block_unresolved() -> None:
    blocks = pd.DataFrame([block("a", "g1", 2, True), block("b", "g1", 2)])
    triage = pd.DataFrame([
        {"physical_location_group": "g1", "review_tier": "focused_review"}
    ])
    decisions = pd.DataFrame(columns=list(decision("g1", "a")))
    crosswalk, _, unresolved, summary = resolve_competition_locations(
        blocks, triage, decisions
    )
    assert crosswalk["competition_location_action"].eq("pending_manual_review").all()
    assert len(unresolved) == 1
    assert summary["analysis_status"] == "pilot_location_resolution_incomplete"


def test_resolution_rejects_canonical_key_from_another_block() -> None:
    blocks = pd.DataFrame([
        block("a", "g1", 2, True), block("b", "g1", 2), block("other", "g0", 1, True)
    ])
    triage = pd.DataFrame([
        {"physical_location_group": "g1", "review_tier": "complex_review"}
    ])
    decisions = pd.DataFrame([decision("g1", "other")])
    with pytest.raises(ValueError, match="outside block"):
        resolve_competition_locations(blocks, triage, decisions)


def test_resolution_rejects_duplicate_block_decisions() -> None:
    blocks = pd.DataFrame([block("a", "g1", 2, True), block("b", "g1", 2)])
    triage = pd.DataFrame([
        {"physical_location_group": "g1", "review_tier": "complex_review"}
    ])
    decisions = pd.DataFrame([decision("g1", "a"), decision("g1", "a")])
    with pytest.raises(ValueError, match="one row per"):
        resolve_competition_locations(blocks, triage, decisions)
