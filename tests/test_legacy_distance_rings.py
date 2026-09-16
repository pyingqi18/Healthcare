import numpy as np
import pandas as pd
import pytest

from medical_ratings.legacy_distance_rings import (
    EARTH_RADIUS_MILES,
    build_legacy_distance_ring_exposures,
)


def _longitude_for_miles(miles: float) -> float:
    return np.degrees(miles / EARTH_RADIUS_MILES)


def _clinics() -> pd.DataFrame:
    distances = [0.0, 0.5, 1.0, 3.0, 6.0]
    return pd.DataFrame(
        {
            "clinic_key": ["focal", "inner", "middle", "outer", "far"],
            "search_location": ["m1", "m1", "m1", "m1", "m2"],
            "entry_year": [2019, 2020, 2020, 2020, 2020],
            "latitude": [0.0] * 5,
            "longitude": [_longitude_for_miles(value) for value in distances],
            "spatial_analysis_eligible": [True] * 5,
        }
    )


def _panel() -> pd.DataFrame:
    rows = []
    for clinic_key in ["focal", "inner", "middle", "outer", "far"]:
        for year in [2020, 2021, 2024, 2025]:
            rows.append({"clinic_key": clinic_key, "year": year})
    return pd.DataFrame(rows)


def test_legacy_rings_assign_boundaries_once() -> None:
    result, _ = build_legacy_distance_ring_exposures(_panel(), _clinics())
    focal_2021 = result[
        (result["clinic_key"] == "focal") & (result["year"] == 2021)
    ].iloc[0]

    assert focal_2021["shock_0_05_count"] == 1
    assert focal_2021["shock_05_2_count"] == 1
    assert focal_2021["shock_2_5_count"] == 1
    assert (
        focal_2021[
            ["shock_0_05_count", "shock_05_2_count", "shock_2_5_count"]
        ].sum()
        == 3
    )


def test_legacy_rings_exclude_self_before_counting() -> None:
    result, _ = build_legacy_distance_ring_exposures(_panel(), _clinics())
    focal_2020 = result[
        (result["clinic_key"] == "focal") & (result["year"] == 2020)
    ].iloc[0]

    assert focal_2020["density_0_05_count"] == 1


def test_legacy_rings_retain_global_cross_market_query() -> None:
    clinics = _clinics()
    clinics.loc[clinics["clinic_key"] == "far", "longitude"] = (
        _longitude_for_miles(4.0)
    )
    _, metadata = build_legacy_distance_ring_exposures(_panel(), clinics)

    assert metadata["cross_market_directed_neighbor_links"] > 0
    assert metadata["neighbor_scope"] == "global_across_markets"


def test_legacy_rings_leave_2025_without_exposure() -> None:
    result, metadata = build_legacy_distance_ring_exposures(
        _panel(), _clinics()
    )

    assert result.loc[result["year"] == 2025, "log_shock_0_05"].isna().all()
    assert metadata["panel_2025_rows_without_exposure"] == 5


def test_legacy_rings_reject_duplicate_clinic_keys() -> None:
    clinics = pd.concat([_clinics(), _clinics().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate clinic_key"):
        build_legacy_distance_ring_exposures(_panel(), clinics)
