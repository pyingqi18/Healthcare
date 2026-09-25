from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from medical_ratings.legacy_regression_report import (
    build_legacy_regression_report,
    collect_regression_coefficients,
    prepare_legacy_report_data,
)


def regions() -> dict[str, dict[str, object]]:
    states = ["NY", "CA", "GA"]
    sizes = ["Small", "Mid_Size", "Large", "Small", "Large"]
    output: dict[str, dict[str, object]] = {}
    for index in range(15):
        state = states[index // 5]
        output[f"Market_{index:02d}"] = {
            "state": state,
            "size": sizes[index % 5],
            "zip_values": [10000 + index],
        }
    return output


def report_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    clinic_rows = []
    panel_rows = []
    strict_rows = []
    for index, market in enumerate(regions()):
        clinic_key = f"clinic-{index:02d}"
        rating = 3.2 + (index % 5) * 0.35
        clinic_rows.append(
            {
                "clinic_key": clinic_key,
                "rating_value": rating,
                "zip": str(10000 + index),
                "search_location": "wrong_market",
                "category": "Dentist" if index % 2 == 0 else "Orthodontist",
                "rating_1_star": 1 + index,
                "rating_2_star": 2,
                "rating_3_star": 3,
                "rating_4_star": 4,
                "rating_5_star": 20 + index,
            }
        )
        for year in (2019, 2020, 2021):
            row = {
                "clinic_key": clinic_key,
                "year": year,
                "dynamic_rating": rating + 0.02 * (year - 2019),
                "analysis_period": True,
                "spatial_analysis_eligible": True,
                "search_location": market,
            }
            panel_rows.append(row)
            strict_rows.append(
                {
                    **row,
                    "strict_009a_sample": True,
                    "lag_entry_shock_2mi_count_strict_009a_excl_self": (
                        0 if year == 2019 else (index % 3) + 1
                    ),
                }
            )
    return pd.DataFrame(panel_rows), pd.DataFrame(clinic_rows), pd.DataFrame(strict_rows)


def write_regression_fixture(root: Path) -> None:
    files = {
        "legacy_2mile/legacy_2mile_coefficients.csv": pd.DataFrame(
            {
                "term": ["log_lag_entry_shock_2mi"],
                "coefficient": [0.036456],
                "standard_error": [0.005123],
                "t_statistic": [7.1159],
                "p_value": [1.14e-12],
            }
        ),
        "strict_009a_self_excluded_2mile/strict_009a_legacy_vs_self_excluded.csv": pd.DataFrame(
            {
                "term": ["two_mile_prior_year_entry_shock"],
                "strict_legacy_coefficient": [0.036],
                "strict_legacy_standard_error": [0.005],
                "strict_legacy_t_statistic": [7.2],
                "strict_legacy_p_value": [1e-12],
                "self_excluded_coefficient": [0.034],
                "self_excluded_standard_error": [0.0052],
                "self_excluded_t_statistic": [6.5],
                "self_excluded_p_value": [1e-10],
            }
        ),
        "strict_009a_entity_year_fe/strict_009a_entity_vs_entity_year_fe.csv": pd.DataFrame(
            {
                "term": ["two_mile_prior_year_entry_shock"],
                "entity_fe_coefficient": [0.034],
                "entity_fe_standard_error": [0.0052],
                "entity_fe_t_statistic": [6.5],
                "entity_fe_p_value": [1e-10],
                "entity_year_fe_coefficient": [0.006],
                "entity_year_fe_standard_error": [0.0059],
                "entity_year_fe_t_statistic": [1.02],
                "entity_year_fe_p_value": [0.31],
            }
        ),
        "strict_009a_market_year_fe/strict_009a_year_vs_market_year_fe.csv": pd.DataFrame(
            {
                "term": ["two_mile_prior_year_entry_shock"],
                "entity_year_fe_coefficient": [0.006],
                "entity_year_fe_standard_error": [0.0059],
                "entity_year_fe_t_statistic": [1.02],
                "entity_year_fe_p_value": [0.31],
                "entity_market_year_fe_coefficient": [0.002],
                "entity_market_year_fe_standard_error": [0.0062],
                "entity_market_year_fe_t_statistic": [0.32],
                "entity_market_year_fe_p_value": [0.75],
            }
        ),
        "distance_rings/legacy_distance_rings_coefficients.csv": pd.DataFrame(
            {
                "model": ["joint_rings"],
                "term": ["log_entry_shock_0_0p5mi"],
                "coefficient": [0.032335],
                "standard_error": [0.005894],
                "t_statistic": [5.49],
                "p_value": [4.15e-8],
            }
        ),
        "strict_spatial_suite/strict_spatial_coefficients.csv": pd.DataFrame(
            {
                "method": ["rings"],
                "fixed_effects": ["entity"],
                "term": ["log_density_0_0p5mi"],
                "coefficient": [-0.040658],
                "standard_error": [0.0284],
                "t_statistic": [-1.43],
                "p_value": [0.1523],
            }
        ),
    }
    for relative, frame in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)


def test_prepare_report_data_uses_actual_zip_market_and_preserves_outcome_identity() -> None:
    panel, clinics, strict = report_inputs()
    clinic_data, panel_data, _ = prepare_legacy_report_data(
        panel, clinics, regions(), strict_panel=strict
    )
    assert len(clinic_data) == 15
    assert set(clinic_data["market"]) == set(regions())
    assert panel_data["clinic_key"].nunique() == 15
    assert panel_data.duplicated(["clinic_key", "year"]).sum() == 0


def test_prepare_report_data_rejects_duplicate_clinic_year() -> None:
    panel, clinics, strict = report_inputs()
    panel = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate clinic-year"):
        prepare_legacy_report_data(panel, clinics, regions(), strict_panel=strict)


def test_collect_regression_coefficients_normalizes_model_variants(tmp_path: Path) -> None:
    write_regression_fixture(tmp_path)
    coefficients, missing = collect_regression_coefficients(tmp_path)
    assert {
        "compatible_2mile_entity",
        "strict_2mile_self_excluded_entity",
        "strict_2mile_self_excluded_entity_year",
        "strict_2mile_self_excluded_market_year",
        "strict_rings_entity",
    }.issubset(set(coefficients["model_id"]))
    row = coefficients.loc[
        coefficients["model_id"].eq("compatible_2mile_entity")
    ].iloc[0]
    assert row["ci95_lower"] == pytest.approx(0.036456 - 1.96 * 0.005123)
    assert row["statistically_significant_5pct"]
    assert isinstance(missing, list)


def test_build_report_writes_fixed_figure_suite_tables_and_metadata(tmp_path: Path) -> None:
    panel, clinics, strict = report_inputs()
    results_root = tmp_path / "results"
    write_regression_fixture(results_root)
    output = tmp_path / "report"
    metadata = build_legacy_regression_report(
        panel=panel,
        clinics=clinics,
        strict_panel=strict,
        regions=regions(),
        results_root=results_root,
        output_directory=output,
    )
    assert (output / "legacy_regression_report.md").exists()
    assert (output / "tables" / "regression_coefficients_long.csv").exists()
    assert len(list((output / "figures").glob("*.png"))) >= 14
    saved = json.loads((output / "legacy_regression_report_metadata.json").read_text())
    assert saved["regression_balltree_modified"] is False
    assert metadata["automatic_model_selection_performed"] is False
