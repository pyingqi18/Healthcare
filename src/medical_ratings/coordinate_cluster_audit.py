"""Audit co-located clinic identities before constructing competition exposure."""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd

from .identifiers import normalize_name, normalize_zip
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


def _cluster_id(market: str, latitude: float, longitude: float) -> str:
    value = f"{market}|{latitude:.7f}|{longitude:.7f}"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"coordinate_cluster:{digest}"


def audit_coordinate_clusters(
    clinics: pd.DataFrame,
    *,
    distance_threshold_meters: float = 50.0,
    clinic_key: str = "clinic_key",
    market_column: str = "search_location",
    latitude_column: str = "latitude",
    longitude_column: str = "longitude",
    eligibility_column: str = "spatial_analysis_eligible",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return exact-coordinate clusters and close pairs without merging them."""

    required = {
        clinic_key,
        market_column,
        latitude_column,
        longitude_column,
        eligibility_column,
    }
    missing = required - set(clinics.columns)
    if missing:
        raise KeyError(f"Missing coordinate audit columns: {sorted(missing)}")
    if distance_threshold_meters <= 0:
        raise ValueError("distance_threshold_meters must be positive")
    if clinics[clinic_key].duplicated().any():
        raise ValueError("Clinic keys must be unique before coordinate auditing")

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

    optional_columns = [
        column
        for column in ("title", "address", "zip", "normalized_zip", "phone", "domain")
        if column in clinics.columns
    ]
    selected_columns = [clinic_key, market_column, *optional_columns]
    work = clinics.loc[included, selected_columns].copy()
    work[latitude_column] = latitude.loc[included]
    work[longitude_column] = longitude.loc[included]
    work["coordinate_latitude_7dp"] = work[latitude_column].round(7)
    work["coordinate_longitude_7dp"] = work[longitude_column].round(7)

    coordinate_group_columns = [
        market_column,
        "coordinate_latitude_7dp",
        "coordinate_longitude_7dp",
    ]
    group_sizes = work.groupby(coordinate_group_columns)[clinic_key].transform("size")
    exact_rows = work.loc[group_sizes.gt(1)].copy()
    if exact_rows.empty:
        exact_rows["coordinate_cluster_id"] = pd.Series(dtype="string")
        exact_rows["coordinate_cluster_size"] = pd.Series(dtype="int64")
    else:
        exact_rows["coordinate_cluster_id"] = exact_rows.apply(
            lambda row: _cluster_id(
                str(row[market_column]),
                float(row["coordinate_latitude_7dp"]),
                float(row["coordinate_longitude_7dp"]),
            ),
            axis=1,
        )
        exact_rows["coordinate_cluster_size"] = group_sizes.loc[exact_rows.index]
        exact_rows = exact_rows.sort_values(
            [market_column, "coordinate_cluster_id", clinic_key]
        ).reset_index(drop=True)

    pair_records: list[dict[str, Any]] = []
    for market, group in work.groupby(market_column, sort=True):
        group = group.reset_index(drop=True)
        distances_miles = haversine_distance_matrix(
            group[latitude_column].to_numpy(),
            group[longitude_column].to_numpy(),
        )
        left_indices, right_indices = np.triu_indices(len(group), k=1)
        pair_distances_meters = (
            distances_miles[left_indices, right_indices] * 1609.344
        )
        selected = pair_distances_meters <= distance_threshold_meters

        for left_index, right_index, distance in zip(
            left_indices[selected],
            right_indices[selected],
            pair_distances_meters[selected],
            strict=True,
        ):
            left = group.iloc[int(left_index)]
            right = group.iloc[int(right_index)]
            record: dict[str, Any] = {
                "market": str(market),
                "left_clinic_key": left[clinic_key],
                "right_clinic_key": right[clinic_key],
                "distance_meters": float(distance),
                "exact_coordinates": bool(distance <= 0.01),
            }
            for column in optional_columns:
                record[f"left_{column}"] = left[column]
                record[f"right_{column}"] = right[column]
            if "title" in optional_columns:
                record["same_normalized_title"] = (
                    normalize_name(left["title"])
                    == normalize_name(right["title"])
                )
            if "address" in optional_columns:
                left_address = normalize_name(left["address"])
                right_address = normalize_name(right["address"])
                record["same_normalized_address"] = (
                    left_address is not None
                    and left_address == right_address
                )
            zip_column = (
                "normalized_zip"
                if "normalized_zip" in optional_columns
                else "zip" if "zip" in optional_columns else None
            )
            if zip_column is not None:
                left_zip = normalize_zip(left[zip_column])
                right_zip = normalize_zip(right[zip_column])
                record["same_normalized_zip"] = (
                    left_zip is not None and left_zip == right_zip
                )
            pair_records.append(record)

    close_pairs = pd.DataFrame.from_records(pair_records)
    if not close_pairs.empty:
        close_pairs = close_pairs.sort_values(
            ["market", "distance_meters", "left_clinic_key", "right_clinic_key"]
        ).reset_index(drop=True)

    market_rows: list[dict[str, Any]] = []
    for market, group in work.groupby(market_column, sort=True):
        market_exact = exact_rows.loc[exact_rows[market_column].eq(market)]
        market_pairs = (
            close_pairs.loc[close_pairs["market"].eq(str(market))]
            if not close_pairs.empty
            else close_pairs
        )
        pair_keys = set()
        if not market_pairs.empty:
            pair_keys.update(market_pairs["left_clinic_key"])
            pair_keys.update(market_pairs["right_clinic_key"])
        market_rows.append(
            {
                market_column: market,
                "clinic_count": int(len(group)),
                "exact_coordinate_cluster_count": int(
                    market_exact["coordinate_cluster_id"].nunique()
                ),
                "clinics_in_exact_coordinate_clusters": int(len(market_exact)),
                "pairs_within_threshold": int(len(market_pairs)),
                "clinics_in_close_pairs": int(len(pair_keys)),
            }
        )
    market_summary = pd.DataFrame.from_records(market_rows)

    all_pair_keys: set[Any] = set()
    if not close_pairs.empty:
        all_pair_keys.update(close_pairs["left_clinic_key"])
        all_pair_keys.update(close_pairs["right_clinic_key"])
    metadata = {
        "input_clinic_rows": int(len(clinics)),
        "spatial_eligible_rows": int(eligible.sum()),
        "included_clinic_rows": int(included.sum()),
        "market_count": int(work[market_column].nunique()),
        "coordinate_rounding_decimals": 7,
        "distance_threshold_meters": float(distance_threshold_meters),
        "exact_coordinate_cluster_count": int(
            exact_rows["coordinate_cluster_id"].nunique()
        ),
        "clinics_in_exact_coordinate_clusters": int(len(exact_rows)),
        "pairs_within_threshold": int(len(close_pairs)),
        "clinics_in_close_pairs": int(len(all_pair_keys)),
        "automatic_merges_performed": 0,
    }
    return exact_rows, close_pairs, market_summary, metadata
