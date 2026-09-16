"""Build conservative competition-counting units without merging outcomes."""

from __future__ import annotations

import hashlib
import re
import unicodedata
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


def normalize_full_address(value: Any) -> str | None:
    """Normalize a full street address while retaining unit information."""

    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "<na>"}:
        return None
    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    text = re.sub(r"#\s*([a-z0-9-]+)", r" unit \1 ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    replacements = {
        "street": "st",
        "avenue": "ave",
        "boulevard": "blvd",
        "road": "rd",
        "drive": "dr",
        "lane": "ln",
        "highway": "hwy",
        "suite": "unit",
        "ste": "unit",
        "apartment": "unit",
        "apt": "unit",
    }
    tokens = [replacements.get(token, token) for token in text.split()]
    return " ".join(tokens) or None


def _identifier(prefix: str, payload: str) -> str:
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"competition_unit:{prefix}:{digest}"


def audit_competition_units(
    clinics: pd.DataFrame,
    *,
    maximum_address_spread_meters: float = 50.0,
    clinic_key: str = "clinic_key",
    market_column: str = "search_location",
    address_column: str = "address",
    latitude_column: str = "latitude",
    longitude_column: str = "longitude",
    eligibility_column: str = "spatial_analysis_eligible",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return a conservative address-based exposure-unit crosswalk.

    Profiles remain separate outcome entities. Profiles share an exposure-counting
    unit only when their normalized full addresses match within a market and all
    coordinates in that address group fall within the configured distance.
    """

    required = {
        clinic_key,
        market_column,
        address_column,
        latitude_column,
        longitude_column,
        eligibility_column,
    }
    missing = required - set(clinics.columns)
    if missing:
        raise KeyError(f"Missing competition-unit columns: {sorted(missing)}")
    if maximum_address_spread_meters <= 0:
        raise ValueError("maximum_address_spread_meters must be positive")
    if clinics[clinic_key].duplicated().any():
        raise ValueError("Clinic keys must be unique before unit construction")

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

    optional = [
        column
        for column in ("title", "zip", "phone", "domain")
        if column in clinics
    ]
    work = clinics.loc[
        included,
        [clinic_key, market_column, address_column, *optional],
    ].copy()
    work[latitude_column] = latitude.loc[included]
    work[longitude_column] = longitude.loc[included]
    work["normalized_full_address"] = work[address_column].map(normalize_full_address)
    work["competition_unit_id"] = pd.Series(index=work.index, dtype="string")
    work["competition_unit_profile_count"] = 1
    work["competition_unit_rule"] = "singleton_missing_address"
    work["outcome_entity_merged"] = False

    conflict_records: list[dict[str, Any]] = []
    addressed = work.loc[work["normalized_full_address"].notna()]
    for (market, address), group in addressed.groupby(
        [market_column, "normalized_full_address"],
        sort=True,
    ):
        keys = sorted(group[clinic_key].astype(str))
        if len(group) == 1:
            index = group.index[0]
            work.loc[index, "competition_unit_id"] = _identifier(
                "clinic", keys[0]
            )
            work.loc[index, "competition_unit_rule"] = "singleton_address"
            continue

        distances = haversine_distance_matrix(
            group[latitude_column].to_numpy(),
            group[longitude_column].to_numpy(),
        )
        maximum_distance_meters = float(np.nanmax(distances) * 1609.344)
        if maximum_distance_meters <= maximum_address_spread_meters:
            identifier = _identifier("address", f"{market}|{address}")
            work.loc[group.index, "competition_unit_id"] = identifier
            work.loc[group.index, "competition_unit_profile_count"] = len(group)
            work.loc[group.index, "competition_unit_rule"] = (
                "shared_exact_normalized_address"
            )
            continue

        conflict_id = _identifier("address_conflict", f"{market}|{address}")
        for index, row in group.iterrows():
            key = str(row[clinic_key])
            work.loc[index, "competition_unit_id"] = _identifier("clinic", key)
            work.loc[index, "competition_unit_rule"] = (
                "singleton_address_coordinate_conflict"
            )
            conflict_records.append(
                {
                    "address_conflict_id": conflict_id,
                    clinic_key: row[clinic_key],
                    market_column: market,
                    address_column: row[address_column],
                    "normalized_full_address": address,
                    latitude_column: row[latitude_column],
                    longitude_column: row[longitude_column],
                    "address_group_profile_count": int(len(group)),
                    "maximum_coordinate_spread_meters": maximum_distance_meters,
                }
            )

    missing_unit = work["competition_unit_id"].isna()
    for index, key in work.loc[missing_unit, clinic_key].items():
        work.loc[index, "competition_unit_id"] = _identifier("clinic", str(key))

    if work["competition_unit_id"].isna().any():
        raise AssertionError("Every included profile must receive a competition unit")

    market_rows: list[dict[str, Any]] = []
    for market, group in work.groupby(market_column, sort=True):
        shared = group["competition_unit_rule"].eq(
            "shared_exact_normalized_address"
        )
        market_rows.append(
            {
                market_column: market,
                "profile_count": int(len(group)),
                "competition_unit_count": int(group["competition_unit_id"].nunique()),
                "profiles_removed_from_exposure_count": int(
                    len(group) - group["competition_unit_id"].nunique()
                ),
                "profiles_in_shared_address_units": int(shared.sum()),
                "shared_address_unit_count": int(
                    group.loc[shared, "competition_unit_id"].nunique()
                ),
                "maximum_profiles_per_unit": int(
                    group.groupby("competition_unit_id").size().max()
                ),
            }
        )

    conflict_columns = [
        "address_conflict_id",
        clinic_key,
        market_column,
        address_column,
        "normalized_full_address",
        latitude_column,
        longitude_column,
        "address_group_profile_count",
        "maximum_coordinate_spread_meters",
    ]
    conflicts = pd.DataFrame.from_records(
        conflict_records,
        columns=conflict_columns,
    )
    market_summary = pd.DataFrame.from_records(market_rows)
    shared = work["competition_unit_rule"].eq("shared_exact_normalized_address")
    conflict_group_count = (
        int(conflicts["address_conflict_id"].nunique())
        if not conflicts.empty
        else 0
    )
    metadata = {
        "analysis_status": "frozen_sensitivity_diagnostic",
        "main_regression_eligible": False,
        "input_clinic_rows": int(len(clinics)),
        "spatial_eligible_rows": int(eligible.sum()),
        "included_profile_rows": int(len(work)),
        "market_count": int(work[market_column].nunique()),
        "maximum_address_spread_meters": float(maximum_address_spread_meters),
        "competition_unit_count": int(work["competition_unit_id"].nunique()),
        "profiles_removed_from_exposure_count": int(
            len(work) - work["competition_unit_id"].nunique()
        ),
        "profiles_in_shared_address_units": int(shared.sum()),
        "shared_address_unit_count": int(
            work.loc[shared, "competition_unit_id"].nunique()
        ),
        "profiles_missing_address": int(
            work["normalized_full_address"].isna().sum()
        ),
        "address_coordinate_conflict_group_count": conflict_group_count,
        "outcome_entity_merges_performed": 0,
    }
    crosswalk = work.sort_values(
        [market_column, "competition_unit_id", clinic_key]
    ).reset_index(drop=True)
    if not conflicts.empty:
        conflicts = conflicts.sort_values(
            [market_column, "address_conflict_id", clinic_key]
        ).reset_index(drop=True)
    return crosswalk, market_summary, conflicts, metadata
