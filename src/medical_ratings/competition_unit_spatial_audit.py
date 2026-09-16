"""Outcome-free spatial-scale diagnostics using competition-counting units."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from .spatial_scale_audit import audit_fixed_radius_scales


def audit_competition_unit_scales(
    crosswalk: pd.DataFrame,
    radii_miles: Sequence[float],
    *,
    clinic_key: str = "clinic_key",
    unit_column: str = "competition_unit_id",
    market_column: str = "search_location",
    latitude_column: str = "latitude",
    longitude_column: str = "longitude",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Count neighboring units and map the counts back to outcome profiles."""

    required = {
        clinic_key,
        unit_column,
        market_column,
        latitude_column,
        longitude_column,
    }
    missing = required - set(crosswalk.columns)
    if missing:
        raise KeyError(
            f"Missing competition-unit spatial columns: {sorted(missing)}"
        )
    if crosswalk.empty:
        raise ValueError("Competition-unit crosswalk is empty")
    if crosswalk[clinic_key].isna().any():
        raise ValueError("Competition-unit crosswalk has missing clinic keys")
    if crosswalk[clinic_key].duplicated().any():
        raise ValueError("Clinic keys must be unique in the unit crosswalk")
    if crosswalk[unit_column].isna().any():
        raise ValueError("Competition-unit crosswalk has missing unit IDs")

    unit_market_counts = crosswalk.groupby(unit_column)[market_column].nunique()
    if unit_market_counts.gt(1).any():
        raise ValueError("A competition unit cannot span multiple markets")

    numeric = crosswalk.copy()
    numeric[latitude_column] = pd.to_numeric(
        numeric[latitude_column], errors="coerce"
    )
    numeric[longitude_column] = pd.to_numeric(
        numeric[longitude_column], errors="coerce"
    )
    if numeric[[latitude_column, longitude_column]].isna().any().any():
        raise ValueError("Competition-unit crosswalk has invalid coordinates")

    units = (
        numeric.groupby(unit_column, sort=True)
        .agg(
            **{
                market_column: (market_column, "first"),
                latitude_column: (latitude_column, "median"),
                longitude_column: (longitude_column, "median"),
                "profile_count": (clinic_key, "size"),
            }
        )
        .reset_index()
    )
    units["spatial_analysis_eligible"] = True

    unit_detail, summary, base_metadata = audit_fixed_radius_scales(
        units,
        radii_miles,
        clinic_key=unit_column,
        market_column=market_column,
        latitude_column=latitude_column,
        longitude_column=longitude_column,
        eligibility_column="spatial_analysis_eligible",
    )
    summary = summary.rename(
        columns={
            "clinic_count": "competition_unit_count",
            "zero_neighbor_clinics": "zero_neighbor_units",
            "zero_neighbor_share": "zero_neighbor_unit_share",
        }
    )

    profile_detail = crosswalk[
        [clinic_key, unit_column, market_column]
    ].merge(
        unit_detail[
            [
                unit_column,
                "radius_miles",
                "neighbor_count",
                "nearest_neighbor_miles",
            ]
        ],
        on=unit_column,
        how="left",
        validate="many_to_many",
    )
    expected_profile_rows = len(crosswalk) * len(base_metadata["radii_miles"])
    if len(profile_detail) != expected_profile_rows:
        raise AssertionError("Profile-level radius mapping did not preserve rows")

    metadata = {
        "analysis_status": "frozen_sensitivity_diagnostic",
        "main_regression_eligible": False,
        "outcomes_used": False,
        "input_profile_rows": int(len(crosswalk)),
        "competition_unit_count": int(len(units)),
        "profiles_removed_from_neighbor_pool": int(len(crosswalk) - len(units)),
        "profile_radius_rows": int(len(profile_detail)),
        "competition_unit_radius_rows": int(len(unit_detail)),
        "market_count": int(units[market_column].nunique()),
        "radii_miles": base_metadata["radii_miles"],
        "unit_coordinate_rule": "median_profile_coordinate",
        "self_profiles_in_same_unit_counted_as_neighbors": False,
        "market_column": market_column,
    }
    return unit_detail, profile_detail, summary, metadata
