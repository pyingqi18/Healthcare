"""Legacy-compatible fixed distance-ring exposure and regressions."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from medical_ratings.legacy_two_mile import (
    EARTH_RADIUS_MILES,
    _boolean_mask,
    _resolve_entry_year,
)


RING_FIELDS = (
    ("0_05", "0_to_0.5", 0.0, 0.5),
    ("05_2", "0.5_to_2", 0.5, 2.0),
    ("2_5", "2_to_5", 2.0, 5.0),
)


def _ring_mask(distances: np.ndarray, lower: float, upper: float) -> np.ndarray:
    if lower == 0.0:
        return distances <= upper
    return (distances > lower) & (distances <= upper)


def build_legacy_distance_ring_exposures(
    panel: pd.DataFrame,
    clinics: pd.DataFrame,
    *,
    clinic_key: str = "clinic_key",
    market_column: str = "search_location",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Reproduce the legacy global 0-0.5, 0.5-2 and 2-5 mile rings."""

    required_panel = {clinic_key, "year"}
    required_clinics = {
        clinic_key,
        market_column,
        "latitude",
        "longitude",
    }
    missing_panel = required_panel - set(panel.columns)
    missing_clinics = required_clinics - set(clinics.columns)
    if missing_panel:
        raise KeyError(f"Missing panel columns: {sorted(missing_panel)}")
    if missing_clinics:
        raise KeyError(f"Missing clinic columns: {sorted(missing_clinics)}")
    if panel.duplicated([clinic_key, "year"]).any():
        raise ValueError("Panel contains duplicate clinic-year rows")
    if clinics[clinic_key].duplicated().any():
        raise ValueError("Clinics contain duplicate clinic_key rows")

    try:
        from sklearn.neighbors import BallTree
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    clinic_work = clinics.copy()
    clinic_work["_entry_year"] = _resolve_entry_year(clinic_work)
    clinic_work["_latitude"] = pd.to_numeric(
        clinic_work["latitude"], errors="coerce"
    )
    clinic_work["_longitude"] = pd.to_numeric(
        clinic_work["longitude"], errors="coerce"
    )
    in_panel = clinic_work[clinic_key].isin(panel[clinic_key].dropna().unique())
    if "spatial_analysis_eligible" in clinic_work.columns:
        spatial_eligible = _boolean_mask(
            clinic_work["spatial_analysis_eligible"]
        )
    else:
        spatial_eligible = pd.Series(True, index=clinic_work.index)
    coordinate_valid = (
        clinic_work["_latitude"].between(-90, 90)
        & clinic_work["_longitude"].between(-180, 180)
        & np.isfinite(clinic_work["_latitude"])
        & np.isfinite(clinic_work["_longitude"])
    )
    market_text = clinic_work[market_column].astype("string").str.strip()
    pool_mask = (
        in_panel
        & spatial_eligible
        & coordinate_valid
        & clinic_work["_entry_year"].notna()
        & market_text.notna()
        & market_text.ne("")
    )
    pool = clinic_work.loc[pool_mask].copy().reset_index(drop=True)
    if pool.empty:
        raise ValueError("No clinics are eligible for the legacy ring pool")

    pool["_entry_year"] = pool["_entry_year"].astype(int)
    coordinates = np.radians(pool[["_latitude", "_longitude"]].to_numpy())
    tree = BallTree(coordinates, metric="haversine")
    neighbor_indices, neighbor_distances = tree.query_radius(
        coordinates,
        r=5.0 / EARTH_RADIUS_MILES,
        return_distance=True,
    )

    output = panel.copy().reset_index(drop=True)
    for legacy_suffix, _, _, _ in RING_FIELDS:
        output[f"shock_{legacy_suffix}_count"] = pd.Series(
            pd.NA, index=output.index, dtype="Int64"
        )
        output[f"density_{legacy_suffix}_count"] = pd.Series(
            pd.NA, index=output.index, dtype="Int64"
        )
        output[f"log_shock_{legacy_suffix}"] = np.nan
        output[f"log_density_{legacy_suffix}"] = np.nan

    panel_groups = output.groupby(clinic_key, sort=False).indices
    pool_keys = pool[clinic_key].to_numpy()
    pool_years = pool["_entry_year"].to_numpy()
    pool_markets = pool[market_column].astype(str).to_numpy()
    cross_market_directed_links = 0
    rows_filled = 0

    for focal_index, focal_key in enumerate(pool_keys):
        positions = panel_groups.get(focal_key)
        if positions is None:
            continue

        indices = neighbor_indices[focal_index]
        distances = neighbor_distances[focal_index] * EARTH_RADIUS_MILES
        not_self = indices != focal_index
        indices = indices[not_self]
        distances = distances[not_self]
        years = pool_years[indices]
        cross_market_directed_links += int(
            np.sum(pool_markets[indices] != pool_markets[focal_index])
        )

        panel_years = pd.to_numeric(
            output.loc[positions, "year"], errors="raise"
        ).astype(int)
        legacy_year_mask = (
            panel_years.ge(pool_years[focal_index])
            & panel_years.lt(2025)
        )
        eligible_positions = np.asarray(positions)[legacy_year_mask.to_numpy()]
        eligible_years = panel_years.loc[legacy_year_mask].to_numpy()
        rows_filled += int(len(eligible_positions))

        for legacy_suffix, _, lower, upper in RING_FIELDS:
            distance_mask = _ring_mask(distances, lower, upper)
            ring_years = years[distance_mask]
            shock_counts = np.asarray(
                [np.sum(ring_years == year - 1) for year in eligible_years],
                dtype=int,
            )
            density_counts = np.asarray(
                [np.sum(ring_years <= year) for year in eligible_years],
                dtype=int,
            )
            output.loc[
                eligible_positions, f"shock_{legacy_suffix}_count"
            ] = shock_counts
            output.loc[
                eligible_positions, f"density_{legacy_suffix}_count"
            ] = density_counts
            output.loc[
                eligible_positions, f"log_shock_{legacy_suffix}"
            ] = np.log1p(shock_counts)
            output.loc[
                eligible_positions, f"log_density_{legacy_suffix}"
            ] = np.log1p(density_counts)

    exposed = output["log_shock_0_05"].notna()
    metadata: dict[str, Any] = {
        "analysis_status": "legacy_ring_reproduction_not_final",
        "algorithm": "legacy_exact_global_fixed_distance_rings",
        "legacy_source": "009a_2026-03-10_all_sanitized.ipynb",
        "input_panel_rows": int(len(panel)),
        "input_clinic_rows": int(len(clinics)),
        "neighbor_pool_clinics": int(len(pool)),
        "panel_rows_with_exposure": int(exposed.sum()),
        "panel_rows_without_exposure": int((~exposed).sum()),
        "panel_rows_filled_by_legacy_year_loop": int(rows_filled),
        "panel_2025_rows_without_exposure": int(
            ((pd.to_numeric(output["year"], errors="coerce") == 2025) & ~exposed).sum()
        ),
        "maximum_radius_miles": 5.0,
        "rings_miles": ["0_to_0.5", "0.5_to_2", "2_to_5"],
        "neighbor_scope": "global_across_markets",
        "self_exclusion": "legacy_row_index_replaced_by_stable_clinic_key_position",
        "legacy_end_year_exclusive": 2025,
        "cross_market_directed_neighbor_links": int(
            cross_market_directed_links
        ),
        "compatibility_changes": [
            "clinic_key replaces the legacy row-order clinic_id",
            "the neighbor pool uses spatially eligible corrected-panel clinics",
            "entry year is read from entry_year or entry_date_proxy",
            "raw ring counts are retained alongside legacy log field names",
        ],
        "legacy_behaviors_retained": [
            "global five-mile neighbor query",
            "three sharp distance rings",
            "self excluded before ring counting",
            "panel years stop at 2024",
        ],
    }
    return output, metadata


def _fit_legacy_ring_model(
    panel: pd.DataFrame,
    *,
    exposure_columns: list[str],
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
        raise KeyError(f"Missing legacy ring regression columns: {missing}")
    mask = pd.Series(True, index=panel.index)
    if "analysis_period" in panel.columns:
        mask &= _boolean_mask(panel["analysis_period"])
    if "spatial_analysis_eligible" in panel.columns:
        mask &= _boolean_mask(panel["spatial_analysis_eligible"])
    model_data = panel.loc[mask].dropna(subset=required).copy()
    if model_data.duplicated(["clinic_key", "year"]).any():
        raise ValueError("Legacy ring sample has duplicate clinic-year rows")
    if model_data.empty:
        raise ValueError("Legacy ring regression sample is empty")

    model_data = model_data.set_index(["clinic_key", "year"]).sort_index()
    formula = (
        "dynamic_rating ~ "
        + " + ".join(exposure_columns)
        + " + log_votes_dynamic + EntityEffects"
    )
    model = PanelOLS.from_formula(
        formula,
        data=model_data,
        drop_absorbed=True,
    )
    result = model.fit(cov_type="clustered", cluster_entity=True)
    metadata = {
        "analysis_status": "legacy_ring_reproduction_not_final",
        "specification_id": specification_id,
        "legacy_source": "009a_2026-03-10_all_sanitized.ipynb",
        "formula": formula,
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
        "time_effects": False,
        "legacy_behaviors_retained": [
            "global five-mile neighbor query",
            "panel years stop at 2024",
        ],
    }
    return result, metadata


def fit_legacy_joint_distance_rings_entity_fe(
    panel: pd.DataFrame,
) -> tuple[Any, dict[str, Any]]:
    """Fit the legacy six-variable joint ring specification."""

    return _fit_legacy_ring_model(
        panel,
        exposure_columns=[
            "log_shock_0_05",
            "log_shock_05_2",
            "log_shock_2_5",
            "log_density_0_05",
            "log_density_05_2",
            "log_density_2_5",
        ],
        specification_id="legacy_joint_distance_rings_entity_fe",
    )


def fit_legacy_half_mile_entity_fe(
    panel: pd.DataFrame,
) -> tuple[Any, dict[str, Any]]:
    """Fit the legacy standalone 0.5-mile specification."""

    return _fit_legacy_ring_model(
        panel,
        exposure_columns=["log_shock_0_05", "log_density_0_05"],
        specification_id="legacy_half_mile_entity_fe",
    )
