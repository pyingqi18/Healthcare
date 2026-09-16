"""Tests for the frozen pre-rebuild final-analysis contract."""

from pathlib import Path

import yaml


def load_contract() -> dict:
    return yaml.safe_load(
        Path("config/final_analysis.yaml").read_text(encoding="utf-8")
    )


def test_main_specification_is_frozen_before_full_rebuild() -> None:
    contract = load_contract()
    status = contract["status"]
    data = contract["data"]
    main = contract["main_specification"]

    assert status["name"] == "frozen_before_full_rebuild"
    assert status["results_authorized"] is False
    assert data["analysis_start_year"] == 2015
    assert data["analysis_end_year"] == 2025
    assert 2026 in data["excluded_partial_years"]
    assert data["market_column"] == "search_location"
    assert main["outcome"] == "dynamic_rating"
    assert main["exposure"]["radius_miles"] == 2.0
    assert main["exposure"]["entry_lag_years"] == 1
    assert main["exposure"]["exclude_focal_entity"] is True
    assert main["density_control"]["timing"] == "end_of_t_minus_2"
    assert main["controls"] == []
    assert main["fixed_effects"] == [
        "clinic_key",
        "search_location_by_year",
    ]


def test_sensitivity_models_preserve_main_sample_and_roles() -> None:
    contract = load_contract()
    common = contract["common_sample"]
    sensitivity = contract["sensitivity_specifications"]
    reporting = contract["reporting"]

    assert common["same_years_across_models"] is True
    assert common["same_entities_across_models"] is True
    assert sensitivity["controls"][0] == {
        "id": "add_log_votes_dynamic",
        "additions": ["log_votes_dynamic"],
        "same_sample_as_main": True,
    }
    assert "fixed_0p5mile" in sensitivity["spatial_methods"]["confirmatory"]
    assert "gravity_inverse_5mile" in sensitivity["spatial_methods"]["exploratory"]
    assert reporting["multiple_testing_adjustment"] == (
        "holm_within_spatial_family"
    )
    assert reporting["prohibit_causal_language_without_additional_identification"] is True


def test_settings_points_to_the_single_analysis_contract() -> None:
    settings = yaml.safe_load(
        Path("config/settings.yaml").read_text(encoding="utf-8")
    )

    assert settings["study"]["minimum_treatment_year"] == 2015
    assert settings["analysis"] == {
        "contract": "config/final_analysis.yaml"
    }
    assert "model" not in settings

