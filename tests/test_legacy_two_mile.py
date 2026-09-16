import pandas as pd
import pytest

from medical_ratings.legacy_two_mile import (
    build_legacy_exact_two_mile_exposures,
)


def _clinics() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": ["a", "b", "c"],
            "search_location": ["m1", "m1", "m2"],
            "entry_year": [2020, 2021, 2021],
            "latitude": [0.0, 0.0, 0.0],
            "longitude": [0.0, 0.01, 0.005],
            "spatial_analysis_eligible": [True, True, True],
        }
    )


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": ["a", "a", "b", "b", "c", "c"],
            "year": [2021, 2022, 2021, 2022, 2021, 2022],
        }
    )


def test_legacy_reproduction_retains_self_counted_entry_shock() -> None:
    result, metadata = build_legacy_exact_two_mile_exposures(
        _panel(), _clinics()
    )

    a_2021 = result[
        (result["clinic_key"] == "a") & (result["year"] == 2021)
    ].iloc[0]
    assert a_2021["lag_entry_shock_2mi_count"] == 1
    assert metadata[
        "panel_rows_potentially_self_counted_as_prior_year_entry"
    ] == 3
    assert metadata["entry_shock_self_excluded"] is False


def test_legacy_reproduction_retains_cross_market_neighbors() -> None:
    result, metadata = build_legacy_exact_two_mile_exposures(
        _panel(), _clinics()
    )

    a_2022 = result[
        (result["clinic_key"] == "a") & (result["year"] == 2022)
    ].iloc[0]
    assert a_2022["lag_entry_shock_2mi_count"] == 2
    assert metadata["cross_market_directed_neighbor_links"] == 4
    assert metadata["neighbor_scope"] == "global_across_markets"


def test_legacy_density_subtracts_self_after_counting() -> None:
    result, _ = build_legacy_exact_two_mile_exposures(
        _panel(), _clinics()
    )

    a_2021 = result[
        (result["clinic_key"] == "a") & (result["year"] == 2021)
    ].iloc[0]
    assert a_2021["density_2mi_total"] == 2


def test_legacy_reproduction_rejects_duplicate_clinic_keys() -> None:
    clinics = pd.concat([_clinics(), _clinics().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate clinic_key"):
        build_legacy_exact_two_mile_exposures(_panel(), clinics)


def test_legacy_reproduction_parses_string_boolean_flags() -> None:
    clinics = _clinics()
    clinics["spatial_analysis_eligible"] = ["True", "False", "True"]
    result, metadata = build_legacy_exact_two_mile_exposures(
        _panel(), clinics
    )
    assert metadata["neighbor_pool_clinics"] == 2
    assert result.loc[
        result["clinic_key"] == "b", "lag_entry_shock_2mi_count"
    ].isna().all()

