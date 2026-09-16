import pandas as pd

from medical_ratings.two_mile_variants import (
    build_self_excluded_two_mile_exposures,
    fit_self_excluded_two_mile_entity_market_year_fe,
    fit_self_excluded_two_mile_entity_time_fe,
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


def test_self_excluded_shock_removes_only_focal_clinic() -> None:
    result, metadata = build_self_excluded_two_mile_exposures(
        _panel(), _clinics()
    )

    a_2021 = result[
        (result["clinic_key"] == "a") & (result["year"] == 2021)
    ].iloc[0]
    a_2022 = result[
        (result["clinic_key"] == "a") & (result["year"] == 2022)
    ].iloc[0]
    assert a_2021["lag_entry_shock_2mi_excl_self_count"] == 0
    assert a_2022["lag_entry_shock_2mi_excl_self_count"] == 2
    assert metadata["panel_rows_with_self_entry_removed"] == 3


def test_self_excluded_shock_preserves_legacy_columns() -> None:
    result, _ = build_self_excluded_two_mile_exposures(
        _panel(), _clinics()
    )

    assert result["lag_entry_shock_2mi_count"].tolist() == [1, 2, 1, 2, 1, 2]


def test_self_excluded_shock_preserves_exposure_missingness() -> None:
    clinics = _clinics()
    clinics.loc[clinics["clinic_key"] == "b", "spatial_analysis_eligible"] = False
    result, _ = build_self_excluded_two_mile_exposures(_panel(), clinics)

    legacy_missing = result["lag_entry_shock_2mi_count"].isna()
    corrected_missing = result[
        "lag_entry_shock_2mi_excl_self_count"
    ].isna()
    assert legacy_missing.equals(corrected_missing)


def test_entity_year_model_keeps_time_varying_control() -> None:
    rows = []
    exposure_values = [0.0, 0.3, 0.1, 0.6, 0.2, 0.8, 0.4, 0.7]
    for clinic_number in range(8):
        for year_offset in range(5):
            exposure = exposure_values[
                (clinic_number + 2 * year_offset) % len(exposure_values)
            ]
            votes = (
                0.07 * ((clinic_number + 1) * (year_offset + 2) % 9)
                + 0.02 * clinic_number
                + 0.03 * year_offset
            )
            residual_pattern = 0.004 * (
                (3 * clinic_number + year_offset) % 5
            )
            rating = (
                3.8
                + 0.05 * exposure
                + 0.03 * votes
                + 0.02 * clinic_number
                + 0.01 * year_offset
                + residual_pattern
            )
            rows.append(
                {
                    "clinic_key": f"clinic_{clinic_number}",
                    "year": 2018 + year_offset,
                    "dynamic_rating": rating,
                    "log_lag_entry_shock_2mi_excl_self": exposure,
                    "log_votes_dynamic": votes,
                    "analysis_period": True,
                    "spatial_analysis_eligible": True,
                }
            )
    panel = pd.DataFrame(rows)

    result, metadata = fit_self_excluded_two_mile_entity_time_fe(panel)

    assert metadata["sample_rows"] == 40
    assert metadata["sample_clinics"] == 8
    assert metadata["entity_effects"] is True
    assert metadata["time_effects"] is True
    assert "TimeEffects" in metadata["formula"]
    assert "log_lag_entry_shock_2mi_excl_self" in result.params.index
    assert "log_votes_dynamic" in result.params.index


def test_market_year_model_uses_market_year_effects() -> None:
    rows = []
    exposure_values = [0.0, 0.3, 0.1, 0.6, 0.2, 0.8, 0.4, 0.7]
    for clinic_number in range(12):
        for year_offset in range(5):
            exposure = exposure_values[
                (clinic_number + 2 * year_offset) % len(exposure_values)
            ]
            votes = (
                0.07 * ((clinic_number + 1) * (year_offset + 2) % 9)
                + 0.02 * clinic_number
                + 0.03 * year_offset
            )
            rating = (
                3.8
                + 0.05 * exposure
                + 0.03 * votes
                + 0.02 * clinic_number
                + 0.01 * year_offset
                + 0.003 * ((clinic_number + year_offset) % 4)
            )
            rows.append(
                {
                    "clinic_key": f"clinic_{clinic_number}",
                    "search_location": f"market_{clinic_number % 3}",
                    "year": 2018 + year_offset,
                    "dynamic_rating": rating,
                    "log_lag_entry_shock_2mi_excl_self": exposure,
                    "log_votes_dynamic": votes,
                    "analysis_period": True,
                    "spatial_analysis_eligible": True,
                }
            )
    panel = pd.DataFrame(rows)

    result, metadata = fit_self_excluded_two_mile_entity_market_year_fe(
        panel
    )

    assert metadata["sample_rows"] == 60
    assert metadata["sample_clinics"] == 12
    assert metadata["market_count"] == 3
    assert metadata["market_year_effect_count"] == 15
    assert metadata["market_year_effects"] is True
    assert "log_lag_entry_shock_2mi_excl_self" in result.params.index
    assert "log_votes_dynamic" in result.params.index
