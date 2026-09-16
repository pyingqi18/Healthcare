"""Tests for conservative competition-counting units."""

import pandas as pd
import pytest

from medical_ratings.competition_units import audit_competition_units


def clinics_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": ["a", "b", "c", "d"],
            "search_location": ["m1", "m1", "m1", "m2"],
            "address": [
                "10 Main Street, Suite 2",
                "10 Main St., Ste 2",
                "10 Main St, Suite 3",
                "10 Main Street, Suite 2",
            ],
            "latitude": [43.0, 43.0001, 43.0, 43.0],
            "longitude": [-76.0, -76.0001, -76.0, -76.0],
            "spatial_analysis_eligible": [True, True, True, True],
            "title": ["Clinic A", "Dr A", "Clinic C", "Clinic D"],
        }
    )


def test_exact_full_address_groups_only_within_market() -> None:
    crosswalk, markets, conflicts, metadata = audit_competition_units(
        clinics_frame()
    )
    indexed = crosswalk.set_index("clinic_key")

    assert indexed.loc["a", "competition_unit_id"] == indexed.loc[
        "b", "competition_unit_id"
    ]
    assert indexed.loc["a", "competition_unit_id"] != indexed.loc[
        "d", "competition_unit_id"
    ]
    assert indexed.loc["c", "competition_unit_profile_count"] == 1
    assert metadata["profiles_removed_from_exposure_count"] == 1
    assert metadata["outcome_entity_merges_performed"] == 0
    assert metadata["analysis_status"] == "frozen_sensitivity_diagnostic"
    assert metadata["main_regression_eligible"] is False
    assert conflicts.empty
    assert markets["profile_count"].sum() == 4


def test_same_address_with_large_coordinate_conflict_stays_separate() -> None:
    clinics = clinics_frame().iloc[:2].copy()
    clinics.loc[1, "latitude"] = 44.0

    crosswalk, _, conflicts, metadata = audit_competition_units(clinics)

    assert crosswalk["competition_unit_id"].nunique() == 2
    assert set(crosswalk["competition_unit_rule"]) == {
        "singleton_address_coordinate_conflict"
    }
    assert len(conflicts) == 2
    assert metadata["address_coordinate_conflict_group_count"] == 1


def test_missing_address_remains_a_singleton() -> None:
    clinics = clinics_frame().iloc[:1].copy()
    clinics.loc[0, "address"] = None

    crosswalk, _, _, metadata = audit_competition_units(clinics)

    assert crosswalk.iloc[0]["competition_unit_rule"] == (
        "singleton_missing_address"
    )
    assert metadata["profiles_missing_address"] == 1


def test_duplicate_clinic_keys_are_rejected() -> None:
    clinics = clinics_frame().iloc[:2].copy()
    clinics.loc[1, "clinic_key"] = "a"

    with pytest.raises(ValueError, match="Clinic keys must be unique"):
        audit_competition_units(clinics)
