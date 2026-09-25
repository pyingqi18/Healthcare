"""Tests for 15-market profile consolidation and location-review preparation."""

from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.cross_source_profile_resolution import (
    apply_profile_decisions_and_build_location_review,
    build_cross_source_profile_review,
)


MARKETS = {f"Market_{index:02d}" for index in range(15)}


def profile_source(prefix: str, *, manual: bool = False) -> pd.DataFrame:
    rows = []
    for index, market in enumerate(sorted(MARKETS)):
        profile_key = f"google:cid:shared-{index}" if prefix != "specialist" else f"google:cid:specialist-{index}"
        rows.append(
            {
                "profile_key": profile_key,
                "requested_location": market,
                "cid": profile_key.rsplit("-", 1)[-1],
                "place_id": "",
                "title": "Business Dental" if prefix != "specialist" else "Specialist Dental",
                "category": "Dentist" if not manual else "Health consultant",
                "address": f"{index} Main St, Example, ST 00000" if prefix != "specialist" else f"{index} Second St, Example, ST 00000",
                "zip": "00000",
                "latitude": 40.0 + index / 100,
                "longitude": -75.0,
                "phone": f"555000{index:04d}",
                "domain": f"dental-{index}.example",
                "url": f"https://dental-{index}.example",
                "votes_count": 10,
                "observation_count": 1,
                "market_assignment_status": "eligible_target_zip",
                "eligibility_review_status": (
                    "manual_category_review" if manual else "include_dental_provider"
                ),
            }
        )
    return pd.DataFrame.from_records(rows)


def reviewed_specialist() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "market",
            "subject_key",
            "decision_type",
            "final_market_assignment_status",
            "final_eligibility_review_status",
        ]
    )


def carry_forward() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": sorted(MARKETS),
            "reference_key": [f"reference:{index}" for index in range(15)],
            "final_discovery_role": ["validated_legacy_carry_forward"] * 15,
        }
    )


def reference_universe() -> pd.DataFrame:
    rows = []
    for index, market in enumerate(sorted(MARKETS)):
        rows.append(
            {
                "clinic_key": f"reference:{index}",
                "search_location": market,
                "title": "Legacy Dental",
                "address": f"{index} Main St, Example, ST 00000",
                "zip": "00000",
                "latitude": 40.0 + index / 100,
                "longitude": -75.0,
                "phone": f"555000{index:04d}",
                "domain": f"dental-{index}.example",
                "reference_source_clinic_keys": f"legacy:{index}:a|legacy:{index}:b",
            }
        )
    return pd.DataFrame.from_records(rows)


def prepared():
    return build_cross_source_profile_review(
        profile_source("business"),
        profile_source("core"),
        profile_source("specialist", manual=True),
        reviewed_specialist(),
        carry_forward(),
        reference_universe(),
        expected_markets=MARKETS,
    )


def test_exact_profiles_are_deduplicated_before_manual_review() -> None:
    inventory, decisions, anchors, lineage, summary = prepared()

    assert len(inventory) == 30
    assert len(decisions) == 15
    assert len(anchors) == 15
    assert not anchors["current_status_individually_verified"].any()
    assert anchors["current_status_sensitivity_required"].all()
    assert len(lineage) == 30
    assert summary["source_profile_rows"] == 45
    assert summary["exact_profile_duplicates_removed"] == 15
    assert summary["automatic_physical_location_merges"] == 0


def test_prior_manual_profile_decision_is_reused_without_re_review() -> None:
    prior = pd.DataFrame(
        {
            "clinic_key": ["google:cid:specialist-0"],
            "reviewed_title": ["Specialist Dental"],
            "manual_decision": ["exclude_non_dentist_category"],
            "manual_reason": ["Previously reviewed as outside the dental sample"],
            "evidence_url": ["https://example.test/evidence"],
            "evidence_checked_at_utc": ["2026-09-10T00:00:00Z"],
        }
    )
    inventory, decisions, _, _, summary = build_cross_source_profile_review(
        profile_source("business"),
        profile_source("core"),
        profile_source("specialist", manual=True),
        reviewed_specialist(),
        carry_forward(),
        reference_universe(),
        expected_markets=MARKETS,
        prior_manual_profile_decisions=prior,
    )

    reused = inventory.loc[
        inventory["profile_key"].eq("google:cid:specialist-0")
    ].iloc[0]
    assert reused["preliminary_profile_status"] == "exclude_non_dentist_category"
    assert reused["profile_status_basis"] == "prior_manual_profile_decision_reused"
    assert reused["prior_manual_profile_decision"] == "exclude_non_dentist_category"
    assert len(decisions) == 14
    assert summary["prior_manual_profile_decisions_reused"] == 1
    assert summary["prior_manual_pending_profiles_resolved"] == 1


def test_prior_manual_profile_decision_rejects_identity_drift() -> None:
    prior = pd.DataFrame(
        {
            "clinic_key": ["google:cid:specialist-0"],
            "reviewed_title": ["Different Business"],
            "manual_decision": ["exclude_non_dentist_category"],
            "manual_reason": ["Previously reviewed"],
            "evidence_url": ["https://example.test/evidence"],
            "evidence_checked_at_utc": ["2026-09-10T00:00:00Z"],
        }
    )
    with pytest.raises(ValueError, match="title mismatch"):
        build_cross_source_profile_review(
            profile_source("business"),
            profile_source("core"),
            profile_source("specialist", manual=True),
            reviewed_specialist(),
            carry_forward(),
            reference_universe(),
            expected_markets=MARKETS,
            prior_manual_profile_decisions=prior,
        )


def test_unanimous_frozen_category_exclusion_skips_redundant_manual_review() -> None:
    specialist = profile_source("specialist", manual=True)
    specialist["category"] = "Dental laboratory"
    category_rules = pd.DataFrame(
        {
            "category": ["Dental laboratory"],
            "category_decision": ["exclude"],
            "reason": ["Auxiliary business rather than a patient-facing clinic"],
        }
    )
    inventory, decisions, _, _, summary = build_cross_source_profile_review(
        profile_source("business"),
        profile_source("core"),
        specialist,
        reviewed_specialist(),
        carry_forward(),
        reference_universe(),
        expected_markets=MARKETS,
        category_rules=category_rules,
    )

    excluded = inventory.loc[
        inventory["profile_key"].str.startswith("google:cid:specialist-")
    ]
    assert excluded["preliminary_profile_status"].eq(
        "exclude_non_dentist_category"
    ).all()
    assert excluded["frozen_category_exclusion_applied"].all()
    assert decisions.empty
    assert summary["frozen_category_exclusions_applied"] == 15


def test_reviewed_profiles_feed_scalable_location_blocks() -> None:
    inventory, template, anchors, _, _ = prepared()
    decisions = template.copy()
    decisions["manual_decision"] = "include_dental_provider"
    decisions["decision_evidence"] = "Reviewed provider website"
    decisions["reviewed_by"] = "tester"
    decisions["reviewed_on"] = "2026-09-19"

    outputs = apply_profile_decisions_and_build_location_review(
        inventory, template, decisions, anchors
    )
    reviewed, profiles, included, pairs, blocks, triage, _, summary = outputs

    assert len(reviewed) == 15
    assert len(profiles) == 30
    assert len(included) == 30
    assert len(pairs) >= 15
    assert len(blocks) == 45
    assert len(triage) == 15
    assert summary["location_candidate_rows"] == 45
    assert summary["automatic_profile_or_location_merges"] == 0
    assert summary["regression_balltree_modified"] is False


def test_profile_decisions_must_cover_every_pending_profile() -> None:
    inventory, template, anchors, _, _ = prepared()
    decisions = template.iloc[:-1].copy()
    decisions["manual_decision"] = "include_dental_provider"
    decisions["decision_evidence"] = "Reviewed"
    decisions["reviewed_by"] = "tester"
    decisions["reviewed_on"] = "2026-09-19"
    with pytest.raises(ValueError, match="exactly cover"):
        apply_profile_decisions_and_build_location_review(
            inventory, template, decisions, anchors
        )
