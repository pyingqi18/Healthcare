import pandas as pd
import pytest

from medical_ratings.spatial_scale_audit import audit_fixed_radius_scales


def test_fixed_radius_counts_are_restricted_to_market() -> None:
    clinics = pd.DataFrame(
        {
            "clinic_key": ["a", "b", "c", "d"],
            "search_location": ["m1", "m1", "m1", "m2"],
            "latitude": [1.0, 1.0, 1.0, 1.0],
            "longitude": [1.0, 1.01, 1.05, 1.005],
            "spatial_analysis_eligible": [True, True, True, True],
        }
    )

    detail, summary, metadata = audit_fixed_radius_scales(
        clinics,
        [1.0, 5.0],
    )

    a_rows = detail.loc[detail["clinic_key"].eq("a")].set_index(
        "radius_miles"
    )
    assert a_rows.loc[1.0, "neighbor_count"] == 1
    assert a_rows.loc[5.0, "neighbor_count"] == 2

    d_rows = detail.loc[detail["clinic_key"].eq("d")]
    assert d_rows["neighbor_count"].eq(0).all()
    assert metadata["outcomes_used"] is False
    assert metadata["market_count"] == 2
    assert "__all_markets__" in set(summary["search_location"])


def test_ineligible_and_invalid_coordinates_are_excluded() -> None:
    clinics = pd.DataFrame(
        {
            "clinic_key": ["a", "b", "c"],
            "search_location": ["m1", "m1", "m1"],
            "latitude": [1.0, None, 1.0],
            "longitude": [1.0, 1.0, 1.01],
            "spatial_analysis_eligible": [True, True, False],
        }
    )

    detail, _, metadata = audit_fixed_radius_scales(clinics, [5.0])

    assert detail["clinic_key"].tolist() == ["a"]
    assert metadata["spatial_eligible_rows"] == 2
    assert metadata["included_clinic_rows"] == 1
    assert metadata["excluded_after_spatial_flag_rows"] == 1


def test_duplicate_clinic_keys_are_rejected() -> None:
    clinics = pd.DataFrame(
        {
            "clinic_key": ["a", "a"],
            "search_location": ["m1", "m1"],
            "latitude": [1.0, 1.01],
            "longitude": [1.0, 1.01],
            "spatial_analysis_eligible": [True, True],
        }
    )

    with pytest.raises(ValueError, match="Clinic keys must be unique"):
        audit_fixed_radius_scales(clinics, [5.0])
