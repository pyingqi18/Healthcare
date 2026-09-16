"""Outcome-free diagnostics for prespecified spatial radii."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from .spatial import haversine_distance_matrix


def _eligible_mask(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False).astype(bool)
    return (
        values.astype("string")
        .str.strip()
        .str.lower()
        .isin({"true", "1", "yes"})
        .fillna(False)
    )


def audit_fixed_radius_scales(
    clinics: pd.DataFrame,
    radii_miles: Sequence[float],
    *,
    clinic_key: str = "clinic_key",
    market_column: str = "search_location",
    latitude_column: str = "latitude",
    longitude_column: str = "longitude",
    eligibility_column: str = "spatial_analysis_eligible",
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Count within-market neighbors without reading any outcome variable."""

    required = {
        clinic_key,
        market_column,
        latitude_column,
        longitude_column,
        eligibility_column,
    }
    missing = required - set(clinics.columns)
    if missing:
        raise KeyError(f"Missing spatial audit columns: {sorted(missing)}")

    radii = sorted({float(radius) for radius in radii_miles})
    if not radii or any(radius <= 0 for radius in radii):
        raise ValueError("At least one positive radius is required")
    if clinics[clinic_key].duplicated().any():
        raise ValueError("Clinic keys must be unique before spatial auditing")

    latitude = pd.to_numeric(clinics[latitude_column], errors="coerce")
    longitude = pd.to_numeric(clinics[longitude_column], errors="coerce")
    valid_coordinates = (
        latitude.between(-90, 90)
        & longitude.between(-180, 180)
        & ~((latitude == 0) & (longitude == 0))
    )
    eligible = _eligible_mask(clinics[eligibility_column])
    included = (
        eligible
        & valid_coordinates
        & clinics[clinic_key].notna()
        & clinics[market_column].notna()
    )

    work = clinics.loc[
        included,
        [clinic_key, market_column],
    ].copy()
    work[latitude_column] = latitude.loc[included]
    work[longitude_column] = longitude.loc[included]

    detail_frames: list[pd.DataFrame] = []
    for market, group in work.groupby(market_column, sort=True):
        group = group.reset_index(drop=True)
        distances = haversine_distance_matrix(
            group[latitude_column].to_numpy(),
            group[longitude_column].to_numpy(),
        )
        np.fill_diagonal(distances, np.inf)
        nearest = distances.min(axis=1)
        nearest[~np.isfinite(nearest)] = np.nan

        for radius in radii:
            detail_frames.append(
                pd.DataFrame(
                    {
                        clinic_key: group[clinic_key],
                        market_column: str(market),
                        "radius_miles": radius,
                        "neighbor_count": (distances <= radius).sum(axis=1),
                        "nearest_neighbor_miles": nearest,
                    }
                )
            )

    detail_columns = [
        clinic_key,
        market_column,
        "radius_miles",
        "neighbor_count",
        "nearest_neighbor_miles",
    ]
    detail = (
        pd.concat(detail_frames, ignore_index=True)
        if detail_frames
        else pd.DataFrame(columns=detail_columns)
    )

    def summarize(group: pd.DataFrame) -> pd.Series:
        counts = group["neighbor_count"]
        nearest = group["nearest_neighbor_miles"].dropna()
        return pd.Series(
            {
                "clinic_count": int(len(group)),
                "zero_neighbor_clinics": int(counts.eq(0).sum()),
                "zero_neighbor_share": float(counts.eq(0).mean()),
                "neighbor_count_mean": float(counts.mean()),
                "neighbor_count_median": float(counts.median()),
                "neighbor_count_p90": float(counts.quantile(0.90)),
                "neighbor_count_maximum": int(counts.max()),
                "nearest_neighbor_median_miles": (
                    float(nearest.median()) if not nearest.empty else None
                ),
                "nearest_neighbor_p90_miles": (
                    float(nearest.quantile(0.90)) if not nearest.empty else None
                ),
            }
        )

    if detail.empty:
        summary = pd.DataFrame()
    else:
        by_market = (
            detail.groupby([market_column, "radius_miles"], sort=True)
            .apply(summarize, include_groups=False)
            .reset_index()
        )
        overall = (
            detail.groupby("radius_miles", sort=True)
            .apply(summarize, include_groups=False)
            .reset_index()
        )
        overall.insert(0, market_column, "__all_markets__")
        summary = pd.concat([overall, by_market], ignore_index=True)
        integer_columns = [
            "clinic_count",
            "zero_neighbor_clinics",
            "neighbor_count_maximum",
        ]
        summary[integer_columns] = summary[integer_columns].astype("int64")

    metadata = {
        "outcomes_used": False,
        "input_clinic_rows": int(len(clinics)),
        "spatial_eligible_rows": int(eligible.sum()),
        "included_clinic_rows": int(included.sum()),
        "excluded_after_spatial_flag_rows": int((eligible & ~included).sum()),
        "market_count": int(work[market_column].nunique()),
        "radii_miles": radii,
        "market_column": market_column,
    }
    return detail, summary, metadata
