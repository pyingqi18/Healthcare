"""Strict corrected-data versions of the remaining 009a spatial methods."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from medical_ratings.strict_legacy_two_mile import (
    EARTH_RADIUS_MILES,
    _resolve_category_eligibility,
    _resolve_entry_years,
    _resolve_market_values,
)


MODEL_EXPOSURES: dict[str, tuple[str, ...]] = {
    "gravity": ("log_gravity_shock", "log_gravity_density"),
    "knn": ("log_dist_nearest_shock", "log_dist_5th_active"),
    "joint_rings": (
        "log_shock_0_05",
        "log_shock_05_2",
        "log_shock_2_5",
        "log_density_0_05",
        "log_density_05_2",
        "log_density_2_5",
    ),
    "half_mile": ("log_shock_0_05", "log_density_0_05"),
}
FIXED_EFFECT_SPECS = ("entity", "entity_year", "entity_market_year")


def _strict_pool(clinics: pd.DataFrame, clinic_key: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {
        clinic_key,
        "category",
        "rating_value",
        "latitude",
        "longitude",
    }
    missing = required - set(clinics.columns)
    if missing:
        raise KeyError(f"Missing strict clinic columns: {sorted(missing)}")
    if clinics[clinic_key].duplicated().any():
        raise ValueError("Clinics contain duplicate clinic_key rows")

    market, market_source, market_rows = _resolve_market_values(clinics)
    entry_year, entry_source, entry_fallback_rows = _resolve_entry_years(
        clinics
    )
    category_eligible, category_counts = _resolve_category_eligibility(
        clinics
    )
    work = clinics.copy()
    work["_rating"] = pd.to_numeric(work["rating_value"], errors="coerce")
    work["_latitude"] = pd.to_numeric(work["latitude"], errors="coerce")
    work["_longitude"] = pd.to_numeric(work["longitude"], errors="coerce")
    work["_entry_year"] = entry_year
    work["_strict_market"] = market
    work["_category_eligible"] = category_eligible
    mask = (
        work["_rating"].notna()
        & work["_latitude"].notna()
        & work["_longitude"].notna()
        & work["_entry_year"].notna()
        & work["_strict_market"].notna()
        & work["_category_eligible"]
    )
    pool = work.loc[mask].copy().reset_index(drop=True)
    if pool.empty:
        raise ValueError("Strict spatial neighbor pool is empty")
    pool["_entry_year"] = pool["_entry_year"].astype(int)
    metadata = {
        "strict_pool_clinics": int(len(pool)),
        "market_source": market_source,
        "market_rows_mapped_from_legacy_zip_rules": int(market_rows),
        "entry_date_source": entry_source,
        "entry_year_rows_filled_from_entry_date_proxy": int(
            entry_fallback_rows
        ),
        **category_counts,
    }
    return pool, metadata


def build_strict_spatial_suite_exposures(
    panel: pd.DataFrame,
    clinics: pd.DataFrame,
    *,
    clinic_key: str = "clinic_key",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build strict 009a gravity, KNN, and ring exposures through 2024."""

    required_panel = {clinic_key, "year"}
    missing_panel = required_panel - set(panel.columns)
    if missing_panel:
        raise KeyError(f"Missing panel columns: {sorted(missing_panel)}")
    if panel.duplicated([clinic_key, "year"]).any():
        raise ValueError("Panel contains duplicate clinic-year rows")

    try:
        from sklearn.neighbors import BallTree
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    pool, pool_metadata = _strict_pool(clinics, clinic_key)
    coordinates = np.radians(pool[["_latitude", "_longitude"]].to_numpy())
    tree = BallTree(coordinates, metric="haversine")
    neighbor_indices, neighbor_distances = tree.query_radius(
        coordinates,
        r=5.0 / EARTH_RADIUS_MILES,
        return_distance=True,
    )

    output = panel.copy().reset_index(drop=True)
    output["strict_spatial_suite_sample"] = False
    output["strict_market"] = pd.Series(pd.NA, index=output.index, dtype="string")
    exposure_columns = sorted(
        {column for columns in MODEL_EXPOSURES.values() for column in columns}
    )
    for column in exposure_columns:
        output[column] = np.nan

    panel_groups = output.groupby(clinic_key, sort=False).indices
    pool_keys = pool[clinic_key].to_numpy()
    pool_years = pool["_entry_year"].to_numpy()
    pool_markets = pool["_strict_market"].astype(str).to_numpy()
    rows_filled = 0
    pool_missing_panel = 0
    cross_market_directed_links = 0

    for focal_index, focal_key in enumerate(pool_keys):
        positions = panel_groups.get(focal_key)
        if positions is None:
            pool_missing_panel += 1
            continue

        indices = neighbor_indices[focal_index]
        distances = (
            neighbor_distances[focal_index] * EARTH_RADIUS_MILES
        )
        not_self = indices != focal_index
        indices = indices[not_self]
        distances = distances[not_self]
        neighbor_years = pool_years[indices]
        cross_market_directed_links += int(
            np.sum(pool_markets[indices] != pool_markets[focal_index])
        )

        positions = np.asarray(positions)
        panel_years = pd.to_numeric(
            output.loc[positions, "year"], errors="raise"
        ).astype(int)
        year_mask = (
            panel_years.ge(pool_years[focal_index])
            & panel_years.lt(2025)
        ).to_numpy()
        eligible_positions = positions[year_mask]
        eligible_years = panel_years.iloc[np.flatnonzero(year_mask)].to_numpy()
        if len(eligible_positions) == 0:
            continue

        rows_filled += int(len(eligible_positions))
        values: dict[str, list[float]] = {
            column: [] for column in exposure_columns
        }
        for year in eligible_years:
            active_distances = distances[neighbor_years <= year]
            shock_distances = distances[neighbor_years == year - 1]

            gravity_density = np.sum(1.0 / (1.0 + active_distances))
            gravity_shock = np.sum(1.0 / (1.0 + shock_distances))
            fifth_active = (
                float(np.sort(active_distances)[4])
                if len(active_distances) >= 5
                else 5.0
            )
            nearest_shock = (
                float(np.min(shock_distances))
                if len(shock_distances) >= 1
                else 5.0
            )
            active_0_05 = np.sum(active_distances <= 0.5)
            active_05_2 = np.sum(
                (active_distances > 0.5) & (active_distances <= 2.0)
            )
            active_2_5 = np.sum(
                (active_distances > 2.0) & (active_distances <= 5.0)
            )
            shock_0_05 = np.sum(shock_distances <= 0.5)
            shock_05_2 = np.sum(
                (shock_distances > 0.5) & (shock_distances <= 2.0)
            )
            shock_2_5 = np.sum(
                (shock_distances > 2.0) & (shock_distances <= 5.0)
            )

            values["log_gravity_density"].append(
                float(np.log1p(gravity_density))
            )
            values["log_gravity_shock"].append(
                float(np.log1p(gravity_shock))
            )
            values["log_dist_5th_active"].append(
                float(np.log1p(fifth_active))
            )
            values["log_dist_nearest_shock"].append(
                float(np.log1p(nearest_shock))
            )
            values["log_density_0_05"].append(float(np.log1p(active_0_05)))
            values["log_density_05_2"].append(float(np.log1p(active_05_2)))
            values["log_density_2_5"].append(float(np.log1p(active_2_5)))
            values["log_shock_0_05"].append(float(np.log1p(shock_0_05)))
            values["log_shock_05_2"].append(float(np.log1p(shock_05_2)))
            values["log_shock_2_5"].append(float(np.log1p(shock_2_5)))

        output.loc[eligible_positions, "strict_spatial_suite_sample"] = True
        output.loc[eligible_positions, "strict_market"] = pool_markets[
            focal_index
        ]
        for column, column_values in values.items():
            output.loc[eligible_positions, column] = column_values

    sample = output["strict_spatial_suite_sample"]
    metadata: dict[str, Any] = {
        "analysis_status": "strict_spatial_method_suite_not_final",
        "legacy_source": "archive/2026/009a_2026-03-10_all_sanitized.ipynb",
        "input_panel_rows": int(len(panel)),
        "input_clinic_rows": int(len(clinics)),
        **pool_metadata,
        "pool_clinics_missing_from_panel": int(pool_missing_panel),
        "panel_rows_with_spatial_suite_exposure": int(sample.sum()),
        "panel_rows_without_spatial_suite_exposure": int((~sample).sum()),
        "maximum_radius_miles": 5.0,
        "year_generation_end_exclusive": 2025,
        "neighbor_scope": "global_across_markets",
        "self_excluded": True,
        "cross_market_directed_neighbor_links": int(
            cross_market_directed_links
        ),
        "methods": list(MODEL_EXPOSURES),
        "fixed_effect_specs": list(FIXED_EFFECT_SPECS),
        "legacy_choices_preserved": [
            "five-mile BallTree supplies all alternative distance methods",
            "focal clinic is excluded before exposure construction",
            "gravity weight is one divided by one plus distance",
            "KNN fallback distance is five miles",
            "rings are zero-to-half, half-to-two, and two-to-five miles",
            "exposure years stop at 2024",
        ],
        "corrected_data_substitutions": [
            "stable clinic_key replaces row-order clinic_id",
            "corrected panel outcome replaces title-and-ZIP review linkage",
            "entry_date_proxy supplies corrected entry timing",
        ],
    }
    return output, metadata


def fit_strict_spatial_model(
    panel: pd.DataFrame,
    *,
    method: str,
    fixed_effects: str,
) -> tuple[Any, dict[str, Any]]:
    """Fit one registered strict spatial model and fixed-effect structure."""

    if method not in MODEL_EXPOSURES:
        raise ValueError(f"Unknown spatial method: {method}")
    if fixed_effects not in FIXED_EFFECT_SPECS:
        raise ValueError(f"Unknown fixed-effect specification: {fixed_effects}")
    try:
        from linearmodels.panel import PanelOLS
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    exposures = list(MODEL_EXPOSURES[method])
    required = [
        "clinic_key",
        "year",
        "dynamic_rating",
        "log_votes_dynamic",
        "strict_spatial_suite_sample",
        *exposures,
    ]
    if fixed_effects == "entity_market_year":
        required.append("strict_market")
    missing = [column for column in required if column not in panel.columns]
    if missing:
        raise KeyError(f"Missing strict spatial model columns: {missing}")

    complete_columns = [
        column
        for column in required
        if column != "strict_spatial_suite_sample"
    ]
    model_data = panel.loc[
        panel["strict_spatial_suite_sample"].eq(True)
    ].dropna(subset=complete_columns)
    model_data = model_data.copy()
    if model_data.duplicated(["clinic_key", "year"]).any():
        raise ValueError("Strict spatial model has duplicate clinic-year rows")
    if model_data.empty:
        raise ValueError("Strict spatial regression sample is empty")

    model_data = model_data.set_index(["clinic_key", "year"]).sort_index()
    formula = (
        "dynamic_rating ~ "
        + " + ".join(exposures)
        + " + log_votes_dynamic + EntityEffects"
    )
    if fixed_effects == "entity_year":
        formula += " + TimeEffects"
        model = PanelOLS.from_formula(
            formula, data=model_data, drop_absorbed=True
        )
    elif fixed_effects == "entity_market_year":
        model_data["market_year"] = (
            model_data["strict_market"].astype(str)
            + "_"
            + model_data.index.get_level_values("year").astype(str)
        )
        market_year = pd.DataFrame(
            model_data["market_year"].astype("category").cat.codes,
            index=model_data.index,
            columns=["market_year"],
        )
        exogenous = model_data[[*exposures, "log_votes_dynamic"]]
        model = PanelOLS(
            model_data["dynamic_rating"],
            exogenous,
            entity_effects=True,
            other_effects=market_year,
            drop_absorbed=True,
        )
        formula += " + MarketYearEffects(strict ZIP market x year)"
    else:
        model = PanelOLS.from_formula(
            formula, data=model_data, drop_absorbed=True
        )
    result = model.fit(cov_type="clustered", cluster_entity=True)

    metadata: dict[str, Any] = {
        "analysis_status": "strict_spatial_method_suite_not_final",
        "specification_id": f"strict_{method}_{fixed_effects}",
        "method": method,
        "fixed_effects_specification": fixed_effects,
        "formula": formula,
        "exposure_columns": exposures,
        "sample_rows": int(len(model_data)),
        "sample_clinics": int(
            model_data.index.get_level_values("clinic_key").nunique()
        ),
        "minimum_year": int(
            model_data.index.get_level_values("year").min()
        ),
        "maximum_year": int(
            model_data.index.get_level_values("year").max()
        ),
        "cluster": "clinic_key",
        "entity_effects": True,
        "time_effects": fixed_effects == "entity_year",
        "market_year_effects": fixed_effects == "entity_market_year",
        "log_votes_dynamic_included": True,
    }
    if fixed_effects == "entity_market_year":
        metadata["market_count"] = int(
            model_data["strict_market"].nunique()
        )
        metadata["market_year_effect_count"] = int(
            model_data["market_year"].nunique()
        )
    return result, metadata
