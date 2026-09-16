import pandas as pd
import pytest

from medical_ratings.strict_legacy_sample_audit import (
    audit_strict_legacy_sample,
)


def _clinics() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": ["a", "b", "c", "d", "e"],
            "category": ["keywords_General_Dentist"] * 5,
            "replacement_source": ["legacy"] * 5,
            "title": ["A", "B", "C", "D", "E"],
            "rating_value": [4.5, 4.0, None, 3.5, 4.5],
            "latitude": [0.0] * 5,
            "longitude": [0.0, 0.01, 0.02, 0.03, 0.04],
            "entry_date_proxy": [
                "2020-01-01",
                "2020-01-01",
                "2020-01-01",
                "2020-01-01",
                "2026-01-01",
            ],
            "zip": ["14201", "14201", "14201", "L2A 5M4", "10001"],
            "search_location": ["m1"] * 5,
            "analysis_exclusion_reason": [
                "eligible",
                "eligible",
                "eligible",
                "outside_target_geography",
                "eligible",
            ],
            "spatial_exclusion_reason": [
                "eligible",
                "invalid_coordinate",
                "eligible",
                "eligible",
                "eligible",
            ],
            "spatial_analysis_eligible": [True, False, True, True, True],
        }
    )


def _base_panel() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "clinic_key": key,
                "year": year,
                "dynamic_rating": 4.0,
                "log_votes_dynamic": 1.0,
                "analysis_period": True,
                "spatial_analysis_eligible": key != "b",
            }
            for key in ["a", "b", "c"]
            for year in [2021, 2022]
        ]
    )


def _strict_panel() -> pd.DataFrame:
    panel = _base_panel()
    panel["strict_009a_sample"] = panel["clinic_key"].isin(["a", "b"])
    panel["log_lag_entry_shock_2mi_strict_009a"] = panel[
        "strict_009a_sample"
    ].map({True: 0.5, False: None})
    return panel


def _compatible_panel() -> pd.DataFrame:
    panel = _base_panel()
    panel["log_lag_entry_shock_2mi"] = panel["clinic_key"].isin(
        ["a", "c"]
    ).map({True: 0.5, False: None})
    return panel


def test_audit_separates_strict_and_compatible_pools() -> None:
    _, _, summary, metadata = audit_strict_legacy_sample(
        _base_panel(), _clinics(), _strict_panel(), _compatible_panel()
    )

    counts = summary.set_index("pool_relation")["clinic_count"].to_dict()
    assert counts == {
        "both": 1,
        "compatible_only": 1,
        "neither": 1,
        "strict_only": 2,
    }
    assert metadata["strict_pool_clinics"] == 3
    assert metadata["compatible_pool_clinics"] == 2


def test_audit_identifies_strict_pool_clinics_missing_from_panel() -> None:
    _, missing, _, metadata = audit_strict_legacy_sample(
        _base_panel(), _clinics(), _strict_panel(), _compatible_panel()
    )

    reasons = missing.set_index("clinic_key")[
        "strict_pool_missing_panel_reason"
    ].to_dict()
    assert reasons == {"e": "entry_after_2025"}
    assert metadata["strict_pool_clinics_missing_from_panel"] == 1


def test_audit_confirms_non_us_postal_is_outside_strict_pool() -> None:
    detail, _, _, _ = audit_strict_legacy_sample(
        _base_panel(), _clinics(), _strict_panel(), _compatible_panel()
    )

    non_us = detail.loc[detail["clinic_key"] == "d"].iloc[0]
    assert not non_us["strict_pool"]
    assert non_us["strict_pool_reason"] == "missing_market"


def test_audit_separates_unknown_from_corrected_business_category() -> None:
    clinics = _clinics()
    clinics.loc[clinics["clinic_key"] == "a", "category"] = "Dentist"
    clinics.loc[
        clinics["clinic_key"] == "a", "replacement_source"
    ] = "corrected_location_rescrape"
    clinics.loc[clinics["clinic_key"] == "b", "category"] = "Unknown"

    detail, _, _, metadata = audit_strict_legacy_sample(
        _base_panel(), clinics, _strict_panel(), _compatible_panel()
    )

    by_key = detail.set_index("clinic_key")
    assert by_key.loc["a", "strict_category_eligible"]
    assert not by_key.loc["b", "strict_category_eligible"]
    assert metadata["corrected_replacement_category_rows"] == 1


def test_audit_compares_regression_rows_on_identical_keys() -> None:
    _, _, _, metadata = audit_strict_legacy_sample(
        _base_panel(), _clinics(), _strict_panel(), _compatible_panel()
    )

    assert metadata["strict_regression_rows"] == 4
    assert metadata["compatible_regression_rows"] == 4
    assert metadata["regression_rows_in_both"] == 2
    assert metadata["strict_only_regression_rows"] == 2
    assert metadata["compatible_only_regression_rows"] == 2


def test_audit_rejects_changed_panel_keys() -> None:
    strict_panel = _strict_panel().iloc[:-1].copy()
    with pytest.raises(ValueError, match="same clinic-years"):
        audit_strict_legacy_sample(
            _base_panel(), _clinics(), strict_panel, _compatible_panel()
        )
