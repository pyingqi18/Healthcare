import pandas as pd
import pytest

from medical_ratings.strict_legacy_two_mile import (
    build_strict_legacy_two_mile_on_corrected_data,
)


def _clinics() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": ["a", "b", "c", "d"],
            "category": ["keywords_General_Dentist"] * 4,
            "replacement_source": ["legacy"] * 4,
            "rating_value": [4.5, 4.0, None, 5.0],
            "latitude": [0.0, 0.0, 0.0, 0.0],
            "longitude": [0.0, 0.01, 0.005, 0.015],
            "entry_date_proxy": [
                "2020-01-01",
                "2021-01-01",
                "2021-01-01",
                "2021-01-01",
            ],
            "zip": ["14201", "14201", "14201", "13201"],
            "search_location": ["m1", "m1", "m1", "m2"],
            "spatial_analysis_eligible": [True, False, True, True],
        }
    )


def _panel() -> pd.DataFrame:
    rows = []
    for key in ["a", "b", "c", "d"]:
        for year in [2019, 2020, 2021, 2022, 2026]:
            rows.append(
                {
                    "clinic_key": key,
                    "year": year,
                    "analysis_period": False,
                }
            )
    return pd.DataFrame(rows)


def test_strict_pool_requires_current_rating() -> None:
    result, metadata = build_strict_legacy_two_mile_on_corrected_data(
        _panel(), _clinics()
    )

    assert metadata["legacy_pool_clinics"] == 3
    assert not result.loc[result["clinic_key"] == "c", "strict_009a_sample"].any()


def test_strict_pool_ignores_later_spatial_eligibility_flag() -> None:
    result, metadata = build_strict_legacy_two_mile_on_corrected_data(
        _panel(), _clinics()
    )

    assert result.loc[
        (result["clinic_key"] == "b") & (result["year"] == 2021),
        "strict_009a_sample",
    ].item()
    assert metadata["spatial_analysis_eligible_filter_applied"] is False


def test_strict_sample_uses_entry_through_2025_without_analysis_mask() -> None:
    result, metadata = build_strict_legacy_two_mile_on_corrected_data(
        _panel(), _clinics()
    )

    a = result.loc[result["clinic_key"] == "a"].set_index("year")
    assert not a.loc[2019, "strict_009a_sample"]
    assert a.loc[2020, "strict_009a_sample"]
    assert a.loc[2022, "strict_009a_sample"]
    assert not a.loc[2026, "strict_009a_sample"]
    assert metadata["analysis_period_filter_applied"] is False


def test_strict_exposure_retains_global_self_counting() -> None:
    result, metadata = build_strict_legacy_two_mile_on_corrected_data(
        _panel(), _clinics()
    )

    a_2022 = result.loc[
        (result["clinic_key"] == "a") & (result["year"] == 2022)
    ].iloc[0]
    assert a_2022["lag_entry_shock_2mi_count_strict_009a"] == 2
    assert metadata["entry_shock_self_excluded"] is False
    assert metadata["cross_market_directed_neighbor_links"] == 4


def test_strict_builder_rejects_duplicate_clinic_identity() -> None:
    clinics = pd.concat([_clinics(), _clinics().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate clinic_key"):
        build_strict_legacy_two_mile_on_corrected_data(_panel(), clinics)


def test_strict_builder_rebuilds_market_from_zip() -> None:
    clinics = _clinics()
    clinics["start_date"] = pd.NA
    clinics["mapped_location"] = pd.NA

    _, metadata = build_strict_legacy_two_mile_on_corrected_data(
        _panel(), clinics
    )

    assert metadata["legacy_pool_clinics"] == 3
    assert metadata["market_column_used"] == "legacy_009a_zip_mapping"
    assert metadata["entry_date_column_used"] == (
        "start_date_then_entry_date_proxy"
    )
    assert metadata["market_rows_mapped_from_legacy_zip_rules"] == 4
    assert metadata["entry_year_rows_filled_from_entry_date_proxy"] == 4


def test_strict_builder_excludes_non_us_postal_from_legacy_market() -> None:
    clinics = _clinics()
    clinics.loc[clinics["clinic_key"] == "d", "zip"] = "L2A 5M4"

    result, metadata = build_strict_legacy_two_mile_on_corrected_data(
        _panel(), clinics
    )

    assert metadata["legacy_pool_clinics"] == 2
    assert not result.loc[
        result["clinic_key"] == "d", "strict_009a_sample"
    ].any()


def test_strict_builder_preserves_audited_corrected_category() -> None:
    clinics = _clinics()
    clinics.loc[clinics["clinic_key"] == "b", "category"] = "Dentist"
    clinics.loc[
        clinics["clinic_key"] == "b", "replacement_source"
    ] = "corrected_location_rescrape"

    result, metadata = build_strict_legacy_two_mile_on_corrected_data(
        _panel(), clinics
    )

    assert result.loc[
        (result["clinic_key"] == "b") & (result["year"] == 2021),
        "strict_009a_sample",
    ].item()
    assert metadata["corrected_replacement_category_rows"] == 1


def test_strict_builder_excludes_legacy_unknown_category() -> None:
    clinics = _clinics()
    clinics.loc[clinics["clinic_key"] == "b", "category"] = "Unknown"

    result, metadata = build_strict_legacy_two_mile_on_corrected_data(
        _panel(), clinics
    )

    assert not result.loc[
        result["clinic_key"] == "b", "strict_009a_sample"
    ].any()
    assert metadata["category_ineligible_rows"] == 1
