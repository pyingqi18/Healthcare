"""Spatial market and competitor-exposure construction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


EARTH_RADIUS_MILES = 3958.8


def haversine_distance_matrix(latitude: np.ndarray, longitude: np.ndarray) -> np.ndarray:
    """Return pairwise great-circle distances in miles."""

    lat = np.radians(np.asarray(latitude, dtype=float))
    lon = np.radians(np.asarray(longitude, dtype=float))
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(
        dlon / 2
    ) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


@dataclass(frozen=True)
class MarketRadii:
    inner_miles: float
    outer_miles: float


def compute_market_radii(
    clinics: pd.DataFrame,
    *,
    market_column: str = "mapped_location",
    latitude_column: str = "latitude",
    longitude_column: str = "longitude",
    inner_quantile: float = 0.25,
    outer_quantile: float = 0.50,
) -> dict[str, MarketRadii]:
    """Compute sample-dependent distance quantiles within each market."""

    radii: dict[str, MarketRadii] = {}
    for market, group in clinics.groupby(market_column):
        valid = group.dropna(subset=[latitude_column, longitude_column])
        if len(valid) < 2:
            radii[str(market)] = MarketRadii(0.0, 0.0)
            continue
        distances = haversine_distance_matrix(
            valid[latitude_column].to_numpy(), valid[longitude_column].to_numpy()
        )
        pairwise = distances[np.triu_indices(len(valid), k=1)]
        radii[str(market)] = MarketRadii(
            inner_miles=float(np.quantile(pairwise, inner_quantile)),
            outer_miles=float(np.quantile(pairwise, outer_quantile)),
        )
    return radii


def add_entry_exposures(
    panel: pd.DataFrame,
    clinics: pd.DataFrame,
    radii: dict[str, MarketRadii],
    *,
    clinic_key: str = "clinic_key",
    market_column: str = "mapped_location",
    entry_year_column: str = "entry_year",
    strong_at_entry_column: str | None = None,
) -> pd.DataFrame:
    """Add lagged entry counts and active density using within-market neighbors."""

    required = [
        clinic_key,
        market_column,
        entry_year_column,
        "latitude",
        "longitude",
    ]
    missing = [column for column in required if column not in clinics.columns]
    if missing:
        raise KeyError(f"Missing spatial clinic columns: {missing}")

    clinic_data = clinics.dropna(subset=required).copy()
    output = panel.copy()
    exposure_frames: list[pd.DataFrame] = []

    for market, market_clinics in clinic_data.groupby(market_column):
        market_clinics = market_clinics.reset_index(drop=True)
        distances = haversine_distance_matrix(
            market_clinics["latitude"].to_numpy(),
            market_clinics["longitude"].to_numpy(),
        )
        market_radii = radii[str(market)]

        for index, clinic in market_clinics.iterrows():
            rows = output[output[clinic_key] == clinic[clinic_key]][[clinic_key, "year"]].copy()
            if rows.empty:
                continue
            competitor_mask = market_clinics[clinic_key].to_numpy() != clinic[clinic_key]
            competitor_years = market_clinics[entry_year_column].astype(int).to_numpy()

            inner_mask = competitor_mask & (distances[index] <= market_radii.inner_miles)
            outer_mask = competitor_mask & (distances[index] <= market_radii.outer_miles)
            ring_mask = outer_mask & ~inner_mask

            rows["entry_shock_inner_count"] = rows["year"].map(
                lambda year: int(np.sum(inner_mask & (competitor_years == year - 1)))
            )
            rows["entry_shock_outer_ring_count"] = rows["year"].map(
                lambda year: int(np.sum(ring_mask & (competitor_years == year - 1)))
            )
            rows["density_inner_count"] = rows["year"].map(
                lambda year: int(np.sum(inner_mask & (competitor_years <= year)))
            )
            rows["density_outer_ring_count"] = rows["year"].map(
                lambda year: int(np.sum(ring_mask & (competitor_years <= year)))
            )

            if strong_at_entry_column is not None:
                if strong_at_entry_column not in market_clinics.columns:
                    raise KeyError(f"Missing {strong_at_entry_column}")
                strong = market_clinics[strong_at_entry_column].fillna(False).astype(bool).to_numpy()
                rows["strong_entry_shock_inner_count"] = rows["year"].map(
                    lambda year: int(
                        np.sum(inner_mask & strong & (competitor_years == year - 1))
                    )
                )

            exposure_frames.append(rows)

    if not exposure_frames:
        return output

    exposures = pd.concat(exposure_frames, ignore_index=True)
    output = output.merge(exposures, on=[clinic_key, "year"], how="left")
    count_columns = [column for column in exposures if column.endswith("_count")]
    output[count_columns] = output[count_columns].fillna(0)
    for column in count_columns:
        output[f"log_{column}"] = np.log1p(output[column])
    return output
