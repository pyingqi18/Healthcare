"""Legacy-compatible fixed two-mile exposure and regression reproduction."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


EARTH_RADIUS_MILES = 3958.8


def _boolean_mask(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(False).astype(bool)
    normalized = values.astype("string").str.strip().str.lower()
    invalid = normalized.notna() & ~normalized.isin(["true", "false"])
    if invalid.any():
        examples = sorted(normalized.loc[invalid].dropna().unique())[:5]
        raise ValueError(f"Invalid boolean values: {examples}")
    return normalized.eq("true").fillna(False)


def _resolve_entry_year(clinics: pd.DataFrame) -> pd.Series:
    if "entry_year" in clinics.columns:
        return pd.to_numeric(clinics["entry_year"], errors="coerce")
    if "entry_date_proxy" in clinics.columns:
        return pd.to_datetime(
            clinics["entry_date_proxy"], errors="coerce"
        ).dt.year
    raise KeyError("Clinics require entry_year or entry_date_proxy")


def build_legacy_exact_two_mile_exposures(
    panel: pd.DataFrame,
    clinics: pd.DataFrame,
    *,
    radius_miles: float = 2.0,
    clinic_key: str = "clinic_key",
    market_column: str = "search_location",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Reproduce the legacy global-neighbor two-mile exposure algorithm.

    This function intentionally retains the two known legacy behaviors needed
    for an exact algorithm comparison: neighbors are queried globally rather
    than within market, and the numeric prior-year entry count includes self.
    The returned metadata quantifies both problems.
    """

    if radius_miles <= 0:
        raise ValueError("radius_miles must be positive")

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
    entry_valid = clinic_work["_entry_year"].notna()
    market_valid = (
        clinic_work[market_column].astype("string").str.strip().notna()
        & clinic_work[market_column].astype("string").str.strip().ne("")
    )
    pool_mask = (
        in_panel
        & spatial_eligible
        & coordinate_valid
        & entry_valid
        & market_valid
    )
    pool = clinic_work.loc[pool_mask].copy().reset_index(drop=True)
    if pool.empty:
        raise ValueError("No clinics are eligible for the legacy neighbor pool")

    pool["_entry_year"] = pool["_entry_year"].astype(int)
    coordinates = np.radians(pool[["_latitude", "_longitude"]].to_numpy())
    tree = BallTree(coordinates, metric="haversine")
    neighbor_indices = tree.query_radius(
        coordinates,
        r=radius_miles / EARTH_RADIUS_MILES,
    )

    output = panel.copy().reset_index(drop=True)
    output["lag_entry_shock_2mi_count"] = pd.Series(
        pd.NA, index=output.index, dtype="Int64"
    )
    output["log_lag_entry_shock_2mi"] = np.nan
    output["lag_entry_shock_2mi_dummy"] = pd.Series(
        pd.NA, index=output.index, dtype="Int64"
    )
    output["density_2mi_total"] = pd.Series(
        pd.NA, index=output.index, dtype="Int64"
    )
    output["log_density_2mi_total"] = np.nan

    panel_groups = output.groupby(clinic_key, sort=False).indices
    pool_keys = pool[clinic_key].to_numpy()
    pool_years = pool["_entry_year"].to_numpy()
    pool_markets = pool[market_column].astype(str).to_numpy()

    cross_market_directed_links = 0
    self_contaminated_rows = 0

    for index, focal_key in enumerate(pool_keys):
        positions = panel_groups.get(focal_key)
        if positions is None:
            continue

        neighbors = neighbor_indices[index]
        neighbor_years = pool_years[neighbors]
        cross_market_directed_links += int(
            np.sum(pool_markets[neighbors] != pool_markets[index])
        )

        years = pd.to_numeric(
            output.loc[positions, "year"], errors="raise"
        ).astype(int)
        lag_counts = np.asarray(
            [np.sum(neighbor_years == year - 1) for year in years],
            dtype=int,
        )
        density_counts = np.asarray(
            [max(0, int(np.sum(neighbor_years <= year)) - 1) for year in years],
            dtype=int,
        )

        output.loc[positions, "lag_entry_shock_2mi_count"] = lag_counts
        output.loc[positions, "log_lag_entry_shock_2mi"] = np.log1p(lag_counts)
        output.loc[positions, "lag_entry_shock_2mi_dummy"] = (
            lag_counts > 0
        ).astype(int)
        output.loc[positions, "density_2mi_total"] = density_counts
        output.loc[positions, "log_density_2mi_total"] = np.log1p(
            density_counts
        )
        self_contaminated_rows += int(
            np.sum(years.to_numpy() == pool_years[index] + 1)
        )

    exposed = output["lag_entry_shock_2mi_count"].notna()
    metadata: dict[str, Any] = {
        "analysis_status": "legacy_reproduction_not_final",
        "algorithm": "legacy_exact_global_two_mile",
        "input_panel_rows": int(len(panel)),
        "input_clinic_rows": int(len(clinics)),
        "neighbor_pool_clinics": int(len(pool)),
        "panel_rows_with_exposure": int(exposed.sum()),
        "panel_rows_without_exposure": int((~exposed).sum()),
        "radius_miles": float(radius_miles),
        "earth_radius_miles": EARTH_RADIUS_MILES,
        "neighbor_scope": "global_across_markets",
        "density_self_handling": "subtract_one_after_counting",
        "entry_shock_self_excluded": False,
        "cross_market_directed_neighbor_links": int(
            cross_market_directed_links
        ),
        "panel_rows_potentially_self_counted_as_prior_year_entry": int(
            self_contaminated_rows
        ),
        "compatibility_changes": [
            "clinic_key replaces the legacy row-order clinic_id",
            "neighbor pool is restricted to spatially eligible clinic keys present in the corrected panel",
            "entry year is read from entry_year or entry_date_proxy",
        ],
        "alerts": [
            "cross_market_neighbors_are_retained_for_legacy_reproduction",
            "numeric_entry_shock_retains_legacy_self_counting",
            "results_must_not_be_reported_as_final",
        ],
    }
    return output, metadata


def fit_legacy_two_mile_entity_fe(panel: pd.DataFrame) -> tuple[Any, dict[str, Any]]:
    """Fit the legacy entity-FE rating model with clinic-clustered errors."""

    try:
        from linearmodels.panel import PanelOLS
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    required = [
        "clinic_key",
        "year",
        "dynamic_rating",
        "log_lag_entry_shock_2mi",
        "log_votes_dynamic",
    ]
    missing = [column for column in required if column not in panel.columns]
    if missing:
        raise KeyError(f"Missing legacy regression columns: {missing}")

    mask = pd.Series(True, index=panel.index)
    if "analysis_period" in panel.columns:
        mask &= _boolean_mask(panel["analysis_period"])
    if "spatial_analysis_eligible" in panel.columns:
        mask &= _boolean_mask(panel["spatial_analysis_eligible"])

    model_data = panel.loc[mask].dropna(subset=required).copy()
    if model_data.duplicated(["clinic_key", "year"]).any():
        raise ValueError("Legacy regression sample has duplicate clinic-year rows")
    if model_data.empty:
        raise ValueError("Legacy regression sample is empty")

    model_data = model_data.set_index(["clinic_key", "year"]).sort_index()
    formula = (
        "dynamic_rating ~ 1 + log_lag_entry_shock_2mi "
        "+ log_votes_dynamic + EntityEffects"
    )
    model = PanelOLS.from_formula(
        formula,
        data=model_data,
        drop_absorbed=True,
    )
    result = model.fit(cov_type="clustered", cluster_entity=True)
    metadata = {
        "analysis_status": "legacy_reproduction_not_final",
        "specification_id": "legacy_2mile_entity_fe_reproduction",
        "formula": formula,
        "sample_rows": int(len(model_data)),
        "sample_clinics": int(
            model_data.index.get_level_values("clinic_key").nunique()
        ),
        "cluster": "clinic_key",
        "known_exposure_defects_retained": [
            "cross_market_neighbor_counting",
            "entry_shock_self_counting",
        ],
    }
    return result, metadata
