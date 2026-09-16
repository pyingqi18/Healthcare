import pandas as pd

from medical_ratings.strict_two_mile_variants import (
    BASELINE_COUNT,
    BASELINE_LOG,
    CORRECTED_COUNT,
    CORRECTED_LOG,
    build_strict_009a_self_excluded_exposure,
    fit_strict_009a_self_excluded_entity_fe,
    fit_strict_009a_self_excluded_entity_market_year_fe,
    fit_strict_009a_self_excluded_entity_year_fe,
)


def _strict_panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": ["a", "a", "b", "b", "c"],
            "year": [2021, 2022, 2021, 2022, 2022],
            "strict_009a_sample": [True, True, True, True, False],
            BASELINE_COUNT: pd.Series([1, 1, 0, 1, pd.NA], dtype="Int64"),
            BASELINE_LOG: [0.693147, 0.693147, 0.0, 0.693147, float("nan")],
        }
    )


def _clinics() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": ["a", "b", "c"],
            "entry_date_proxy": ["2020-01-01", "2021-01-01", "2020-01-01"],
        }
    )


def test_strict_self_exclusion_changes_only_focal_entry_year_plus_one() -> None:
    result, metadata = build_strict_009a_self_excluded_exposure(
        _strict_panel(), _clinics()
    )

    assert result[CORRECTED_COUNT].tolist()[:4] == [0, 1, 0, 0]
    assert metadata["panel_rows_with_self_entry_removed"] == 2
    assert metadata["entry_shock_self_excluded"] is True


def test_strict_self_exclusion_preserves_frozen_baseline_columns() -> None:
    panel = _strict_panel()
    result, _ = build_strict_009a_self_excluded_exposure(panel, _clinics())

    pd.testing.assert_series_equal(result[BASELINE_COUNT], panel[BASELINE_COUNT])
    pd.testing.assert_series_equal(result[BASELINE_LOG], panel[BASELINE_LOG])
    assert result[CORRECTED_COUNT].isna().equals(panel[BASELINE_COUNT].isna())


def test_strict_self_exclusion_rejects_duplicate_clinic_year() -> None:
    panel = pd.concat([_strict_panel(), _strict_panel().iloc[[0]]])

    try:
        build_strict_009a_self_excluded_exposure(panel, _clinics())
    except ValueError as exc:
        assert "duplicate clinic-year" in str(exc)
    else:
        raise AssertionError("Expected duplicate clinic-year rejection")


def test_strict_self_excluded_model_preserves_strict_formula() -> None:
    rows = []
    exposure_values = [0.0, 0.2, 0.4, 0.1, 0.7, 0.3]
    for clinic_number in range(8):
        for year_offset in range(5):
            exposure = exposure_values[
                (clinic_number + 2 * year_offset) % len(exposure_values)
            ]
            votes = 0.05 * (
                (clinic_number + 1) * (year_offset + 2) % 11
            ) + 0.01 * year_offset
            rating = (
                4.0
                + 0.06 * exposure
                + 0.04 * votes
                + 0.02 * clinic_number
                + 0.003 * ((clinic_number + year_offset) % 4)
            )
            rows.append(
                {
                    "clinic_key": f"clinic_{clinic_number}",
                    "year": 2018 + year_offset,
                    "dynamic_rating": rating,
                    CORRECTED_LOG: exposure,
                    "log_votes_dynamic": votes,
                    "strict_009a_sample": True,
                }
            )
    panel = pd.DataFrame(rows)

    result, metadata = fit_strict_009a_self_excluded_entity_fe(panel)

    assert metadata["sample_rows"] == 40
    assert metadata["sample_clinics"] == 8
    assert metadata["entity_effects"] is True
    assert metadata["time_effects"] is False
    assert metadata["explicit_constant_included"] is False
    assert CORRECTED_LOG in result.params.index
    assert "log_votes_dynamic" in result.params.index


def test_strict_year_fe_model_adds_only_time_effects() -> None:
    rows = []
    exposure_values = [0.0, 0.2, 0.4, 0.1, 0.7, 0.3]
    for clinic_number in range(8):
        for year_offset in range(5):
            exposure = exposure_values[
                (clinic_number + 2 * year_offset) % len(exposure_values)
            ]
            votes = 0.04 * (
                (clinic_number + 2) * (year_offset + 1) % 13
            ) + 0.015 * clinic_number
            rating = (
                4.0
                + 0.05 * exposure
                + 0.03 * votes
                + 0.02 * clinic_number
                + 0.01 * year_offset
                + 0.002 * ((2 * clinic_number + year_offset) % 5)
            )
            rows.append(
                {
                    "clinic_key": f"clinic_{clinic_number}",
                    "year": 2018 + year_offset,
                    "dynamic_rating": rating,
                    CORRECTED_LOG: exposure,
                    "log_votes_dynamic": votes,
                    "strict_009a_sample": True,
                }
            )
    panel = pd.DataFrame(rows)

    result, metadata = fit_strict_009a_self_excluded_entity_year_fe(panel)

    assert metadata["sample_rows"] == 40
    assert metadata["sample_clinics"] == 8
    assert metadata["year_count"] == 5
    assert metadata["entity_effects"] is True
    assert metadata["time_effects"] is True
    assert metadata["explicit_constant_included"] is False
    assert "TimeEffects" in metadata["formula"]
    assert CORRECTED_LOG in result.params.index


def test_strict_market_year_model_uses_legacy_zip_markets() -> None:
    rows = []
    clinics = []
    zipcodes = [12953, 13210, 14210]
    exposure_values = [0.0, 0.2, 0.4, 0.1, 0.7, 0.3]
    for clinic_number in range(12):
        clinic_key = f"clinic_{clinic_number}"
        clinics.append(
            {
                "clinic_key": clinic_key,
                "zip": zipcodes[clinic_number % 3],
                "search_location": "deliberately_wrong_market",
            }
        )
        for year_offset in range(5):
            exposure = exposure_values[
                (clinic_number + 2 * year_offset) % len(exposure_values)
            ]
            votes = 0.04 * (
                (clinic_number + 2) * (year_offset + 1) % 13
            ) + 0.015 * clinic_number
            rating = (
                4.0
                + 0.05 * exposure
                + 0.03 * votes
                + 0.02 * clinic_number
                + 0.01 * year_offset
                + 0.002 * ((2 * clinic_number + year_offset) % 5)
            )
            rows.append(
                {
                    "clinic_key": clinic_key,
                    "year": 2018 + year_offset,
                    "dynamic_rating": rating,
                    CORRECTED_LOG: exposure,
                    "log_votes_dynamic": votes,
                    "strict_009a_sample": True,
                }
            )

    result, metadata = (
        fit_strict_009a_self_excluded_entity_market_year_fe(
            pd.DataFrame(rows), pd.DataFrame(clinics)
        )
    )

    assert metadata["sample_rows"] == 60
    assert metadata["sample_clinics"] == 12
    assert metadata["year_count"] == 5
    assert metadata["market_source"] == "legacy_009a_zip_mapping"
    assert metadata["market_count"] == 3
    assert metadata["market_year_effect_count"] == 15
    assert metadata["entity_effects"] is True
    assert metadata["time_effects"] is False
    assert metadata["market_year_effects"] is True
    assert CORRECTED_LOG in result.params.index
