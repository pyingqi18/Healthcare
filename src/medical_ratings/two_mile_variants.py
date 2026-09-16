"""Corrected and diagnostic variants of the frozen legacy two-mile model."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from medical_ratings.legacy_two_mile import (
    _boolean_mask,
    _resolve_entry_year,
    build_legacy_exact_two_mile_exposures,
)


def build_self_excluded_two_mile_exposures(
    panel: pd.DataFrame,
    clinics: pd.DataFrame,
    *,
    radius_miles: float = 2.0,
    clinic_key: str = "clinic_key",
    market_column: str = "search_location",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Remove only the focal clinic from the legacy prior-year entry shock."""

    output, legacy_metadata = build_legacy_exact_two_mile_exposures(
        panel,
        clinics,
        radius_miles=radius_miles,
        clinic_key=clinic_key,
        market_column=market_column,
    )

    clinic_work = clinics.copy()
    clinic_work["_entry_year"] = _resolve_entry_year(clinic_work)
    entry_year_by_clinic = clinic_work.set_index(clinic_key)["_entry_year"]
    focal_entry_year = output[clinic_key].map(entry_year_by_clinic)
    panel_year = pd.to_numeric(output["year"], errors="coerce")
    legacy_count = output["lag_entry_shock_2mi_count"]
    self_entry_row = (
        legacy_count.notna()
        & focal_entry_year.notna()
        & panel_year.eq(focal_entry_year + 1)
    )

    corrected_count = legacy_count.copy()
    corrected_count.loc[self_entry_row] = (
        corrected_count.loc[self_entry_row].astype(int) - 1
    )
    if (corrected_count.dropna().astype(int) < 0).any():
        raise ValueError("Self-excluded entry shock became negative")

    output["lag_entry_shock_2mi_excl_self_count"] = corrected_count
    output["log_lag_entry_shock_2mi_excl_self"] = np.log1p(
        pd.to_numeric(corrected_count, errors="coerce")
    )
    output["lag_entry_shock_2mi_excl_self_dummy"] = (
        corrected_count.gt(0).astype("Int64")
    )

    metadata: dict[str, Any] = {
        "analysis_status": "single_defect_correction_not_final",
        "algorithm": "legacy_exact_global_two_mile_self_excluded",
        "baseline_module": "medical_ratings.legacy_two_mile",
        "variant_module": "medical_ratings.two_mile_variants",
        "input_panel_rows": int(len(panel)),
        "input_clinic_rows": int(len(clinics)),
        "neighbor_pool_clinics": legacy_metadata["neighbor_pool_clinics"],
        "panel_rows_with_exposure": legacy_metadata[
            "panel_rows_with_exposure"
        ],
        "panel_rows_without_exposure": legacy_metadata[
            "panel_rows_without_exposure"
        ],
        "radius_miles": float(radius_miles),
        "neighbor_scope": legacy_metadata["neighbor_scope"],
        "entry_shock_self_excluded": True,
        "panel_rows_with_self_entry_removed": int(self_entry_row.sum()),
        "cross_market_directed_neighbor_links": legacy_metadata[
            "cross_market_directed_neighbor_links"
        ],
        "changes_from_legacy_reproduction": [
            "the focal clinic is subtracted from its own prior-year entry shock"
        ],
        "unchanged_legacy_choices": [
            "fixed two-mile radius",
            "global neighbor query",
            "density subtracts one after counting",
            "clinic entity fixed effects with clinic-clustered standard errors",
        ],
        "alerts": ["results_remain_a_diagnostic_comparison_not_final"],
    }
    return output, metadata


def _fit_self_excluded_two_mile(
    panel: pd.DataFrame,
    *,
    include_time_effects: bool,
) -> tuple[Any, dict[str, Any]]:
    try:
        from linearmodels.panel import PanelOLS
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    exposure_column = "log_lag_entry_shock_2mi_excl_self"
    required = [
        "clinic_key",
        "year",
        "dynamic_rating",
        exposure_column,
        "log_votes_dynamic",
    ]
    missing = [column for column in required if column not in panel.columns]
    if missing:
        raise KeyError(f"Missing corrected regression columns: {missing}")

    mask = pd.Series(True, index=panel.index)
    if "analysis_period" in panel.columns:
        mask &= _boolean_mask(panel["analysis_period"])
    if "spatial_analysis_eligible" in panel.columns:
        mask &= _boolean_mask(panel["spatial_analysis_eligible"])

    model_data = panel.loc[mask].dropna(subset=required).copy()
    if model_data.duplicated(["clinic_key", "year"]).any():
        raise ValueError("Corrected regression sample has duplicate clinic-year rows")
    if model_data.empty:
        raise ValueError("Corrected regression sample is empty")

    model_data = model_data.set_index(["clinic_key", "year"]).sort_index()
    formula = (
        "dynamic_rating ~ 1 + log_lag_entry_shock_2mi_excl_self "
        "+ log_votes_dynamic + EntityEffects"
    )
    if include_time_effects:
        formula += " + TimeEffects"
    model = PanelOLS.from_formula(
        formula,
        data=model_data,
        drop_absorbed=True,
    )
    result = model.fit(cov_type="clustered", cluster_entity=True)

    if include_time_effects:
        status = "fixed_effect_structure_comparison_not_final"
        specification_id = "self_excluded_2mile_entity_year_fe_comparison"
    else:
        status = "single_defect_correction_not_final"
        specification_id = "self_excluded_2mile_entity_fe_comparison"
    metadata = {
        "analysis_status": status,
        "specification_id": specification_id,
        "baseline_module": "medical_ratings.legacy_two_mile",
        "variant_module": "medical_ratings.two_mile_variants",
        "formula": formula,
        "sample_rows": int(len(model_data)),
        "sample_clinics": int(
            model_data.index.get_level_values("clinic_key").nunique()
        ),
        "cluster": "clinic_key",
        "entity_effects": True,
        "time_effects": include_time_effects,
        "known_exposure_defects_retained": [
            "cross_market_neighbor_counting"
        ],
    }
    return result, metadata


def fit_self_excluded_two_mile_entity_fe(
    panel: pd.DataFrame,
) -> tuple[Any, dict[str, Any]]:
    """Fit the self-excluded model with clinic fixed effects."""

    return _fit_self_excluded_two_mile(
        panel, include_time_effects=False
    )


def fit_self_excluded_two_mile_entity_time_fe(
    panel: pd.DataFrame,
) -> tuple[Any, dict[str, Any]]:
    """Fit the self-excluded model with clinic and year fixed effects."""

    return _fit_self_excluded_two_mile(panel, include_time_effects=True)


def fit_self_excluded_two_mile_entity_market_year_fe(
    panel: pd.DataFrame,
    *,
    market_column: str = "search_location",
) -> tuple[Any, dict[str, Any]]:
    """Fit the self-excluded model with clinic and market-year effects."""

    try:
        from linearmodels.panel import PanelOLS
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    exposure_column = "log_lag_entry_shock_2mi_excl_self"
    required = [
        "clinic_key",
        "year",
        "dynamic_rating",
        exposure_column,
        "log_votes_dynamic",
        market_column,
    ]
    missing = [column for column in required if column not in panel.columns]
    if missing:
        raise KeyError(f"Missing market-year regression columns: {missing}")

    mask = pd.Series(True, index=panel.index)
    if "analysis_period" in panel.columns:
        mask &= _boolean_mask(panel["analysis_period"])
    if "spatial_analysis_eligible" in panel.columns:
        mask &= _boolean_mask(panel["spatial_analysis_eligible"])

    model_data = panel.loc[mask].dropna(subset=required).copy()
    market_text = model_data[market_column].astype("string").str.strip()
    model_data = model_data.loc[market_text.ne("")].copy()
    if model_data.duplicated(["clinic_key", "year"]).any():
        raise ValueError("Market-year sample has duplicate clinic-year rows")
    if model_data.empty:
        raise ValueError("Market-year regression sample is empty")

    model_data["market_year"] = (
        model_data[market_column].astype(str)
        + "_"
        + model_data["year"].astype(str)
    )
    model_data = model_data.set_index(["clinic_key", "year"]).sort_index()
    exogenous = model_data[[exposure_column, "log_votes_dynamic"]].copy()
    exogenous.insert(0, "const", 1.0)
    market_year = pd.DataFrame(
        model_data["market_year"].astype("category").cat.codes,
        index=model_data.index,
        columns=["market_year"],
    )
    model = PanelOLS(
        model_data["dynamic_rating"],
        exogenous,
        entity_effects=True,
        other_effects=market_year,
        drop_absorbed=True,
    )
    result = model.fit(cov_type="clustered", cluster_entity=True)
    formula = (
        "dynamic_rating ~ 1 + log_lag_entry_shock_2mi_excl_self "
        "+ log_votes_dynamic + EntityEffects "
        f"+ MarketYearEffects({market_column} x year)"
    )
    metadata = {
        "analysis_status": "market_year_effect_comparison_not_final",
        "specification_id": (
            "self_excluded_2mile_entity_market_year_fe_comparison"
        ),
        "baseline_module": "medical_ratings.legacy_two_mile",
        "variant_module": "medical_ratings.two_mile_variants",
        "formula": formula,
        "sample_rows": int(len(model_data)),
        "sample_clinics": int(
            model_data.index.get_level_values("clinic_key").nunique()
        ),
        "market_column": market_column,
        "market_count": int(model_data[market_column].nunique()),
        "market_year_effect_count": int(model_data["market_year"].nunique()),
        "cluster": "clinic_key",
        "entity_effects": True,
        "time_effects": False,
        "market_year_effects": True,
        "changes_from_entity_year_variant": [
            "replace common year effects with search-location-by-year effects"
        ],
        "known_exposure_defects_retained": [
            "cross_market_neighbor_counting"
        ],
    }
    return result, metadata
