"""Tests for competition-unit-adjusted fixed-radius diagnostics."""

import pandas as pd
import pytest

from medical_ratings.competition_unit_spatial_audit import (
    audit_competition_unit_scales,
)


def base_crosswalk() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": ["a", "b", "c", "d"],
            "competition_unit_id": ["u1", "u1", "u2", "u3"],
            "search_location": ["m1", "m1", "m1", "m2"],
            "latitude": [1.0, 1.0001, 1.0, 1.0],
            "longitude": [1.0, 1.0001, 1.01, 1.005],
        }
    )


def test_profiles_in_same_unit_are_not_counted_as_neighbors() -> None:
    units, profiles, summary, metadata = audit_competition_unit_scales(
        base_crosswalk(), [1.0]
    )

    unit_counts = units.set_index("competition_unit_id")["neighbor_count"]
    assert unit_counts.loc["u1"] == 1
    assert unit_counts.loc["u2"] == 1
    assert unit_counts.loc["u3"] == 0
    profile_counts = profiles.set_index("clinic_key")["neighbor_count"]
    assert profile_counts.loc["a"] == 1
    assert profile_counts.loc["b"] == 1
    assert metadata["profiles_removed_from_neighbor_pool"] == 1
    assert metadata["self_profiles_in_same_unit_counted_as_neighbors"] is False
    assert metadata["analysis_status"] == "frozen_sensitivity_diagnostic"
    assert metadata["main_regression_eligible"] is False
    assert "competition_unit_count" in summary.columns


def test_profile_radius_mapping_preserves_every_profile_and_radius() -> None:
    _, profiles, _, metadata = audit_competition_unit_scales(
        base_crosswalk(), [1.0, 5.0]
    )

    assert len(profiles) == 8
    assert profiles.groupby("clinic_key")["radius_miles"].nunique().eq(2).all()
    assert metadata["profile_radius_rows"] == 8


def test_competition_unit_cannot_span_markets() -> None:
    crosswalk = base_crosswalk()
    crosswalk.loc[1, "search_location"] = "m2"

    with pytest.raises(ValueError, match="cannot span multiple markets"):
        audit_competition_unit_scales(crosswalk, [1.0])


def test_duplicate_clinic_keys_are_rejected() -> None:
    crosswalk = base_crosswalk()
    crosswalk.loc[1, "clinic_key"] = "a"

    with pytest.raises(ValueError, match="Clinic keys must be unique"):
        audit_competition_unit_scales(crosswalk, [1.0])
