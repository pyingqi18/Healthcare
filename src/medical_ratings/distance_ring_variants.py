"""Diagnostic fixed-effect variants of the frozen legacy distance rings."""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from medical_ratings.legacy_two_mile import _boolean_mask


JOINT_RING_EXPOSURES = (
    "log_shock_0_05",
    "log_shock_05_2",
    "log_shock_2_5",
    "log_density_0_05",
    "log_density_05_2",
    "log_density_2_5",
)
HALF_MILE_EXPOSURES = (
    "log_shock_0_05",
    "log_density_0_05",
)


def _fit_ring_entity_year_fe(
    panel: pd.DataFrame,
    *,
    exposure_columns: Sequence[str],
    specification_id: str,
) -> tuple[Any, dict[str, Any]]:
    try:
        from linearmodels.panel import PanelOLS
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    required = [
        "clinic_key",
        "year",
        "dynamic_rating",
        "log_votes_dynamic",
        *exposure_columns,
    ]
    missing = [column for column in required if column not in panel.columns]
    if missing:
        raise KeyError(f"Missing distance-ring variant columns: {missing}")

    mask = pd.Series(True, index=panel.index)
    if "analysis_period" in panel.columns:
        mask &= _boolean_mask(panel["analysis_period"])
    if "spatial_analysis_eligible" in panel.columns:
        mask &= _boolean_mask(panel["spatial_analysis_eligible"])
    model_data = panel.loc[mask].dropna(subset=required).copy()
    if model_data.duplicated(["clinic_key", "year"]).any():
        raise ValueError(
            "Distance-ring variant sample has duplicate clinic-year rows"
        )
    if model_data.empty:
        raise ValueError("Distance-ring variant regression sample is empty")

    model_data = model_data.set_index(["clinic_key", "year"]).sort_index()
    formula = (
        "dynamic_rating ~ "
        + " + ".join(exposure_columns)
        + " + log_votes_dynamic + EntityEffects + TimeEffects"
    )
    model = PanelOLS.from_formula(
        formula,
        data=model_data,
        drop_absorbed=True,
    )
    result = model.fit(cov_type="clustered", cluster_entity=True)
    metadata = {
        "analysis_status": "fixed_effect_structure_comparison_not_final",
        "specification_id": specification_id,
        "baseline_module": "medical_ratings.legacy_distance_rings",
        "variant_module": "medical_ratings.distance_ring_variants",
        "formula": formula,
        "sample_rows": int(len(model_data)),
        "sample_clinics": int(
            model_data.index.get_level_values("clinic_key").nunique()
        ),
        "minimum_year": int(model_data.index.get_level_values("year").min()),
        "maximum_year": int(model_data.index.get_level_values("year").max()),
        "cluster": "clinic_key",
        "entity_effects": True,
        "time_effects": True,
        "changes_from_legacy_ring_reproduction": [
            "add common year fixed effects"
        ],
        "unchanged_legacy_choices": [
            "global five-mile neighbor query",
            "three sharp distance rings",
            "self excluded before ring counting",
            "panel years stop at 2024",
            "clinic-clustered standard errors",
        ],
    }
    return result, metadata


def fit_joint_distance_rings_entity_year_fe(
    panel: pd.DataFrame,
) -> tuple[Any, dict[str, Any]]:
    """Add common year effects to the legacy joint distance-ring model."""

    return _fit_ring_entity_year_fe(
        panel,
        exposure_columns=JOINT_RING_EXPOSURES,
        specification_id="joint_distance_rings_entity_year_fe_comparison",
    )


def fit_half_mile_entity_year_fe(
    panel: pd.DataFrame,
) -> tuple[Any, dict[str, Any]]:
    """Add common year effects to the legacy standalone half-mile model."""

    return _fit_ring_entity_year_fe(
        panel,
        exposure_columns=HALF_MILE_EXPOSURES,
        specification_id="half_mile_entity_year_fe_comparison",
    )


def _fit_ring_entity_market_year_fe(
    panel: pd.DataFrame,
    *,
    exposure_columns: Sequence[str],
    specification_id: str,
    market_column: str,
) -> tuple[Any, dict[str, Any]]:
    try:
        from linearmodels.panel import PanelOLS
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    required = [
        "clinic_key",
        "year",
        "dynamic_rating",
        "log_votes_dynamic",
        market_column,
        *exposure_columns,
    ]
    missing = [column for column in required if column not in panel.columns]
    if missing:
        raise KeyError(f"Missing market-year ring columns: {missing}")

    mask = pd.Series(True, index=panel.index)
    if "analysis_period" in panel.columns:
        mask &= _boolean_mask(panel["analysis_period"])
    if "spatial_analysis_eligible" in panel.columns:
        mask &= _boolean_mask(panel["spatial_analysis_eligible"])
    model_data = panel.loc[mask].dropna(subset=required).copy()
    market_text = model_data[market_column].astype("string").str.strip()
    model_data = model_data.loc[market_text.ne("")].copy()
    if model_data.duplicated(["clinic_key", "year"]).any():
        raise ValueError(
            "Market-year ring sample has duplicate clinic-year rows"
        )
    if model_data.empty:
        raise ValueError("Market-year ring regression sample is empty")

    model_data["market_year"] = (
        model_data[market_column].astype(str)
        + "_"
        + model_data["year"].astype(str)
    )
    model_data = model_data.set_index(["clinic_key", "year"]).sort_index()
    exogenous = model_data[[*exposure_columns, "log_votes_dynamic"]].copy()
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
        "dynamic_rating ~ "
        + " + ".join(exposure_columns)
        + " + log_votes_dynamic + EntityEffects "
        + f"+ MarketYearEffects({market_column} x year)"
    )
    metadata = {
        "analysis_status": "market_year_effect_comparison_not_final",
        "specification_id": specification_id,
        "baseline_module": "medical_ratings.legacy_distance_rings",
        "variant_module": "medical_ratings.distance_ring_variants",
        "formula": formula,
        "sample_rows": int(len(model_data)),
        "sample_clinics": int(
            model_data.index.get_level_values("clinic_key").nunique()
        ),
        "minimum_year": int(model_data.index.get_level_values("year").min()),
        "maximum_year": int(model_data.index.get_level_values("year").max()),
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
        "unchanged_legacy_choices": [
            "global five-mile neighbor query",
            "three sharp distance rings",
            "self excluded before ring counting",
            "panel years stop at 2024",
            "clinic-clustered standard errors",
        ],
    }
    return result, metadata


def fit_joint_distance_rings_entity_market_year_fe(
    panel: pd.DataFrame,
    *,
    market_column: str = "search_location",
) -> tuple[Any, dict[str, Any]]:
    """Replace common year effects with market-year effects for all rings."""

    return _fit_ring_entity_market_year_fe(
        panel,
        exposure_columns=JOINT_RING_EXPOSURES,
        specification_id="joint_distance_rings_entity_market_year_fe_comparison",
        market_column=market_column,
    )


def fit_half_mile_entity_market_year_fe(
    panel: pd.DataFrame,
    *,
    market_column: str = "search_location",
) -> tuple[Any, dict[str, Any]]:
    """Replace common year effects with market-year effects at half a mile."""

    return _fit_ring_entity_market_year_fe(
        panel,
        exposure_columns=HALF_MILE_EXPOSURES,
        specification_id="half_mile_entity_market_year_fe_comparison",
        market_column=market_column,
    )
