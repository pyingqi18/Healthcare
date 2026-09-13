"""Tests for explicit final profile and location resolution."""

import pandas as pd

from medical_ratings.final_location_resolution import (
    apply_location_resolution_decisions,
)


def profiles() -> pd.DataFrame:
    rows = []
    for cid, title, group, canonical, votes in [
        ("1", "Alpha Dental", "g1", True, 100),
        ("2", "Dr Alpha", "g1", False, 5),
        ("3", "Alpha Dental Old", "g2", True, 10),
        ("4", "Pulmonary Office", "g3", True, 1),
    ]:
        rows.append(
            {
                "clinic_key": f"google:cid:{cid}",
                "cid": cid,
                "title": title,
                "mapped_location": "Syracuse_NY_M",
                "physical_location_group": group,
                "suggested_canonical_profile": canonical,
                "profile_role": "organization" if "Dr " not in title else "individual_provider",
                "votes_count": votes,
                "observation_count": 2,
                "address": "10 Main St, Syracuse, NY 13202",
                "phone": "315-555-0100",
                "domain": "alpha.example",
            }
        )
    return pd.DataFrame(rows)


def anomalies() -> pd.DataFrame:
    return profiles().loc[
        lambda frame: frame["cid"].eq("4"), ["clinic_key", "cid", "title"]
    ]


def profile_decisions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "clinic_key": "google:cid:4",
                "cid": "4",
                "reviewed_title": "Pulmonary Office",
                "profile_decision": "exclude_profile",
                "decision_reason": "Confirmed non-dental service",
                "evidence_reference": "https://example.com/profile",
                "evidence_checked_at_utc": "2026-09-10T00:00:00Z",
            }
        ]
    )


def pairs() -> pd.DataFrame:
    return pd.DataFrame(
        [{"left_location_group": "g1", "right_location_group": "g2"}]
    )


def location_decisions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "left_location_group": "g2",
                "right_location_group": "g1",
                "location_decision": "merge_groups",
                "decision_reason": "Same physical practice",
                "evidence_reference": "audit:same_phone",
                "evidence_checked_at_utc": "2026-09-10T00:00:00Z",
            }
        ]
    )


def test_decisions_preserve_crosswalk_and_build_one_canonical_location() -> None:
    crosswalk, locations = apply_location_resolution_decisions(
        profiles(), anomalies(), profile_decisions(), pairs(), location_decisions()
    )

    assert len(crosswalk) == 4
    assert len(locations) == 1
    assert int(crosswalk["final_profile_status"].eq("excluded").sum()) == 1
    assert int(crosswalk["final_location_canonical"].sum()) == 1
    assert locations.iloc[0]["clinic_key"] == "google:cid:1"
    assert int(locations.iloc[0]["final_profile_count"]) == 3
    assert int(locations.iloc[0]["source_location_group_count"]) == 2


def test_profile_decisions_require_complete_anomaly_coverage() -> None:
    try:
        apply_location_resolution_decisions(
            profiles(), anomalies(), profile_decisions().iloc[0:0], pairs(), location_decisions()
        )
    except ValueError as error:
        assert "coverage does not match" in str(error)
    else:
        raise AssertionError("Expected incomplete profile decisions to fail")


def test_location_decisions_require_complete_unique_pair_coverage() -> None:
    try:
        apply_location_resolution_decisions(
            profiles(), anomalies(), profile_decisions(), pairs(), location_decisions().iloc[0:0]
        )
    except ValueError as error:
        assert "coverage does not match" in str(error)
    else:
        raise AssertionError("Expected incomplete location decisions to fail")


def test_keep_separate_preserves_two_active_locations() -> None:
    decisions = location_decisions()
    decisions["location_decision"] = "keep_separate"
    crosswalk, locations = apply_location_resolution_decisions(
        profiles(), anomalies(), profile_decisions(), pairs(), decisions
    )

    assert len(locations) == 2
    assert crosswalk.loc[
        crosswalk["final_profile_status"].eq("included"),
        "final_physical_location_id",
    ].nunique() == 2
