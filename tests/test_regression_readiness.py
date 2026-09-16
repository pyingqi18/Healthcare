import pandas as pd

from medical_ratings.regression_readiness import audit_regression_readiness


def base_panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": ["a", "a", "b", "b"],
            "year": [2020, 2021, 2020, 2021],
            "search_location": ["m1", "m1", "m1", "m1"],
            "dynamic_rating": [4.0, 4.2, 3.8, 3.7],
            "analysis_period": [True, True, True, True],
            "spatial_analysis_eligible": [True, True, True, False],
        }
    )


def test_missing_exposures_are_reported_without_fitting() -> None:
    result = audit_regression_readiness(base_panel())

    assert result["regression_ready"] is False
    assert result["schema"]["missing_model_columns"] == [
        "log_density_inner_count",
        "log_entry_shock_inner_count",
    ]
    assert result["sample"]["analysis_and_spatial_eligible_rows"] == 3
    assert result["sample"]["complete_estimation_rows"] == 0
    assert result["target_specification"]["market_column"] == "search_location"


def test_complete_panel_reports_sample_and_within_variation() -> None:
    panel = base_panel()
    panel["log_entry_shock_inner_count"] = [0.0, 0.7, 0.0, 0.7]
    panel["log_density_inner_count"] = [0.7, 1.1, 0.7, 1.1]

    result = audit_regression_readiness(panel)

    assert result["regression_ready"] is True
    assert result["schema"]["missing_model_columns"] == []
    assert result["sample"]["complete_estimation_rows"] == 3
    assert result["sample"]["complete_estimation_clinics"] == 2
    assert (
        result["variable_diagnostics"]["dynamic_rating"][
            "entities_with_within_variation"
        ]
        == 1
    )


def test_duplicate_entity_year_rows_block_readiness() -> None:
    panel = base_panel()
    panel["log_entry_shock_inner_count"] = [0.0, 0.7, 0.0, 0.7]
    panel["log_density_inner_count"] = [0.7, 1.1, 0.7, 1.1]
    panel = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)

    result = audit_regression_readiness(panel)

    assert result["regression_ready"] is False
    assert result["schema"]["duplicate_entity_year_rows"] == 1
    assert "duplicate_entity_year_rows" in result["alerts"]
