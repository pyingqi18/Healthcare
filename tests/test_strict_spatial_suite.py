import numpy as np
import pandas as pd

from medical_ratings.strict_spatial_suite import (
    MODEL_EXPOSURES,
    build_strict_spatial_suite_exposures,
    fit_strict_spatial_model,
)


def _clinics() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": ["a", "b", "c", "excluded"],
            "category": [
                "keywords_General_Dentist",
                "keywords_Special_Dentist",
                "keywords_Surgery_Dentist",
                "Unknown",
            ],
            "rating_value": [4.5, 4.6, 4.7, 4.8],
            "latitude": [0.0, 0.0, 0.0, 0.0],
            "longitude": [0.0, 0.004, 0.02, 0.001],
            "entry_date_proxy": [
                "2020-01-01",
                "2021-01-01",
                "2021-01-01",
                "2021-01-01",
            ],
            "zip": [12953, 12953, 12953, 12953],
        }
    )


def _panel() -> pd.DataFrame:
    rows = []
    for clinic_key in ["a", "b", "c", "excluded"]:
        for year in range(2020, 2026):
            rows.append({"clinic_key": clinic_key, "year": year})
    return pd.DataFrame(rows)


def test_strict_spatial_suite_preserves_legacy_boundaries() -> None:
    result, metadata = build_strict_spatial_suite_exposures(
        _panel(), _clinics()
    )

    a_2022 = result[
        (result["clinic_key"] == "a") & (result["year"] == 2022)
    ].iloc[0]
    a_2025 = result[
        (result["clinic_key"] == "a") & (result["year"] == 2025)
    ].iloc[0]
    excluded = result[result["clinic_key"] == "excluded"]

    assert metadata["strict_pool_clinics"] == 3
    assert metadata["self_excluded"] is True
    assert a_2022["log_shock_0_05"] == np.log1p(1)
    assert a_2022["log_shock_05_2"] == np.log1p(1)
    assert a_2022["log_shock_2_5"] == 0.0
    assert not bool(a_2025["strict_spatial_suite_sample"])
    assert pd.isna(a_2025["log_gravity_shock"])
    assert not excluded["strict_spatial_suite_sample"].any()


def test_strict_spatial_suite_builds_every_registered_exposure() -> None:
    result, _ = build_strict_spatial_suite_exposures(_panel(), _clinics())

    expected = {
        column for columns in MODEL_EXPOSURES.values() for column in columns
    }
    assert expected.issubset(result.columns)
    sample = result[result["strict_spatial_suite_sample"]]
    assert sample[list(expected)].notna().all().all()


def test_strict_spatial_model_fixed_effect_registry() -> None:
    rows = []
    exposure_columns = sorted(
        {column for columns in MODEL_EXPOSURES.values() for column in columns}
    )
    for clinic_number in range(12):
        for year_offset in range(5):
            row = {
                "clinic_key": f"clinic_{clinic_number}",
                "year": 2018 + year_offset,
                "dynamic_rating": (
                    4.0
                    + 0.01 * clinic_number
                    + 0.005 * year_offset
                    + 0.002 * ((clinic_number + year_offset) % 4)
                ),
                "log_votes_dynamic": (
                    0.03 * ((clinic_number + 2) * (year_offset + 1) % 11)
                    + 0.01 * clinic_number
                ),
                "strict_spatial_suite_sample": True,
                "strict_market": f"market_{clinic_number % 3}",
            }
            for column_number, column in enumerate(exposure_columns):
                row[column] = (
                    0.02
                    * (
                        (clinic_number + 1) * (column_number + 2)
                        + year_offset * (column_number + 3)
                    )
                    % 0.9
                )
            rows.append(row)
    panel = pd.DataFrame(rows)

    for fixed_effects in (
        "entity",
        "entity_year",
        "entity_market_year",
    ):
        result, metadata = fit_strict_spatial_model(
            panel,
            method="gravity",
            fixed_effects=fixed_effects,
        )
        assert metadata["sample_rows"] == 60
        assert metadata["sample_clinics"] == 12
        assert metadata["minimum_year"] == 2018
        assert metadata["maximum_year"] == 2022
        assert metadata["entity_effects"] is True
        assert metadata["time_effects"] == (
            fixed_effects == "entity_year"
        )
        assert metadata["market_year_effects"] == (
            fixed_effects == "entity_market_year"
        )
        assert "log_gravity_shock" in result.params.index
