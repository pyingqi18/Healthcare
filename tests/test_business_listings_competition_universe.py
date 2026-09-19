from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.business_listings_competition_universe import (
    build_pilot_competition_universe,
)


def inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    crosswalk = pd.DataFrame([
        {
            "clinic_key": "org",
            "competition_location_id": "location:new",
            "competition_location_included": True,
            "is_canonical_competition_profile": True,
            "resolution_source": "reviewed",
        },
        {
            "clinic_key": "doctor",
            "competition_location_id": "location:new",
            "competition_location_included": True,
            "is_canonical_competition_profile": False,
            "resolution_source": "reviewed",
        },
    ])
    blocks = pd.DataFrame([
        {
            "clinic_key": key,
            "mapped_location": "Syracuse_NY_M",
            "title": title,
            "address": "10 Main St, Syracuse, NY 13214",
            "zip": "13214",
            "phone": "+13155550100",
            "domain": "new.example",
            "latitude": 43.0,
            "longitude": -76.0,
            "outcome_profile_included": True,
        }
        for key, title in (("org", "New Dental"), ("doctor", "Dr New"))
    ])
    references = pd.DataFrame([
        {
            "reference_key": "legacy",
            "discovered": False,
            "current_benchmark_included": True,
            "historical_panel_included": True,
        }
    ])
    carry = pd.DataFrame([
        {
            "reference_key": "legacy",
            "competition_location_id": "location:legacy",
            "mapped_location": "Syracuse_NY_M",
            "title": "Legacy Dental",
            "address": "20 Main St, Syracuse, NY 13214",
            "zip": "13214",
            "phone": "+13155550200",
            "domain": "legacy.example",
            "latitude": 43.1,
            "longitude": -76.1,
            "coordinate_source": "legacy_crosswalk",
            "evidence_url": "https://example.org/legacy",
            "evidence_checked_at_utc": "2026-09-19T00:00:00Z",
            "manual_reason": "official site confirms current location",
        }
    ])
    return crosswalk, blocks, references, carry


def test_builds_discovered_and_carry_forward_locations_without_new_outcome() -> None:
    locations, profiles, summary = build_pilot_competition_universe(*inputs())
    assert len(locations) == 2
    assert len(profiles) == 3
    carry = locations.loc[locations["location_source"].eq("validated_legacy_carry_forward")].iloc[0]
    assert carry["outcome_profile_count"] == 0
    assert bool(carry["historical_panel_retained"])
    assert summary["business_listings_discovered_locations"] == 1
    assert summary["validated_legacy_carry_forward_locations"] == 1
    assert summary["final_competition_locations"] == 2
    assert summary["business_listings_outcome_profiles"] == 2


def test_requires_exact_coverage_of_valid_undiscovered_references() -> None:
    crosswalk, blocks, references, carry = inputs()
    with pytest.raises(ValueError, match="exactly cover"):
        build_pilot_competition_universe(
            crosswalk, blocks, references, carry.iloc[0:0]
        )


def test_rejects_carry_forward_duplicate_address() -> None:
    crosswalk, blocks, references, carry = inputs()
    carry.loc[0, "address"] = "10 Main St, Syracuse, NY 13214"
    with pytest.raises(ValueError, match="duplicates a discovered location"):
        build_pilot_competition_universe(crosswalk, blocks, references, carry)


def test_requires_one_canonical_profile_per_discovered_location() -> None:
    crosswalk, blocks, references, carry = inputs()
    crosswalk["is_canonical_competition_profile"] = False
    with pytest.raises(ValueError, match="one canonical"):
        build_pilot_competition_universe(crosswalk, blocks, references, carry)
