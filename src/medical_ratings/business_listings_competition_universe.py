"""Build the pilot competition-location universe with validated legacy carry-forwards."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from medical_ratings.identifiers import normalize_name


EARTH_RADIUS_METERS = 6_371_008.8
REQUIRED_CROSSWALK_COLUMNS = {
    "clinic_key",
    "competition_location_id",
    "competition_location_included",
    "is_canonical_competition_profile",
    "resolution_source",
}
REQUIRED_BLOCK_COLUMNS = {
    "clinic_key",
    "mapped_location",
    "title",
    "address",
    "zip",
    "phone",
    "domain",
    "latitude",
    "longitude",
    "outcome_profile_included",
}
REQUIRED_REFERENCE_COLUMNS = {
    "reference_key",
    "discovered",
    "current_benchmark_included",
    "historical_panel_included",
}
REQUIRED_CARRY_COLUMNS = {
    "reference_key",
    "competition_location_id",
    "mapped_location",
    "title",
    "address",
    "zip",
    "phone",
    "domain",
    "latitude",
    "longitude",
    "coordinate_source",
    "evidence_url",
    "evidence_checked_at_utc",
    "manual_reason",
}


def _boolean(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no", "", "nan"}:
            return False
        raise ValueError(f"Cannot interpret boolean value: {value}")
    if value is None or pd.isna(value):
        return False
    return bool(value)


def _require_unique(frame: pd.DataFrame, column: str, label: str) -> None:
    values = frame[column].astype("string").str.strip()
    if values.isna().any() or values.eq("").any() or values.duplicated().any():
        raise ValueError(f"{label} requires unique nonblank {column} values")


def _distance_meters(left: pd.Series, right: pd.Series) -> float | None:
    try:
        lat_1 = float(left["latitude"])
        lon_1 = float(left["longitude"])
        lat_2 = float(right["latitude"])
        lon_2 = float(right["longitude"])
    except (TypeError, ValueError):
        return None
    if any(math.isnan(value) for value in (lat_1, lon_1, lat_2, lon_2)):
        return None
    lat_1, lon_1, lat_2, lon_2 = map(math.radians, (lat_1, lon_1, lat_2, lon_2))
    delta_latitude = lat_2 - lat_1
    delta_longitude = lon_2 - lon_1
    haversine = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(lat_1) * math.cos(lat_2) * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(min(1.0, haversine)))


def build_pilot_competition_universe(
    location_crosswalk: pd.DataFrame,
    location_blocks: pd.DataFrame,
    adjudicated_references: pd.DataFrame,
    carry_forwards: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return final pilot locations and a profile-to-location provenance crosswalk."""

    for frame, required, label in (
        (location_crosswalk, REQUIRED_CROSSWALK_COLUMNS, "Location crosswalk"),
        (location_blocks, REQUIRED_BLOCK_COLUMNS, "Location blocks"),
        (adjudicated_references, REQUIRED_REFERENCE_COLUMNS, "Adjudicated references"),
        (carry_forwards, REQUIRED_CARRY_COLUMNS, "Carry-forward locations"),
    ):
        missing = required - set(frame.columns)
        if missing:
            raise KeyError(f"{label} is missing columns: {sorted(missing)}")

    _require_unique(location_crosswalk, "clinic_key", "Location crosswalk")
    _require_unique(location_blocks, "clinic_key", "Location blocks")
    _require_unique(adjudicated_references, "reference_key", "Adjudicated references")
    _require_unique(carry_forwards, "reference_key", "Carry-forward locations")
    _require_unique(carry_forwards, "competition_location_id", "Carry-forward locations")

    crosswalk_keys = set(location_crosswalk["clinic_key"].astype(str))
    block_keys = set(location_blocks["clinic_key"].astype(str))
    if crosswalk_keys != block_keys:
        raise ValueError(
            "Location crosswalk and blocks must contain identical clinic_key values"
        )
    if not location_crosswalk["competition_location_included"].map(_boolean).all():
        raise ValueError("Pilot universe input contains excluded competition profiles")

    valid_undiscovered = adjudicated_references.loc[
        adjudicated_references["current_benchmark_included"].map(_boolean)
        & ~adjudicated_references["discovered"].map(_boolean),
        "reference_key",
    ].astype(str)
    expected_carry = set(valid_undiscovered)
    actual_carry = set(carry_forwards["reference_key"].astype(str))
    if actual_carry != expected_carry:
        raise ValueError(
            "Carry-forward file must exactly cover valid undiscovered references; "
            f"missing={sorted(expected_carry - actual_carry)}, "
            f"extra={sorted(actual_carry - expected_carry)}"
        )

    joined = location_crosswalk.merge(
        location_blocks,
        on="clinic_key",
        how="left",
        validate="one_to_one",
        suffixes=("_resolution", ""),
    )
    canonical_counts = joined.groupby("competition_location_id")[
        "is_canonical_competition_profile"
    ].apply(lambda values: int(values.map(_boolean).sum()))
    if not canonical_counts.eq(1).all():
        raise ValueError("Every discovered competition location requires one canonical profile")

    discovered_records: list[dict[str, Any]] = []
    for location_id, group in joined.groupby("competition_location_id", sort=True):
        canonical = group.loc[group["is_canonical_competition_profile"].map(_boolean)].iloc[0]
        discovered_records.append(
            {
                "competition_location_id": str(location_id),
                "mapped_location": str(canonical["mapped_location"]),
                "title": canonical["title"],
                "address": canonical["address"],
                "zip": canonical["zip"],
                "phone": canonical["phone"],
                "domain": canonical["domain"],
                "latitude": canonical["latitude"],
                "longitude": canonical["longitude"],
                "location_source": "business_listings_live",
                "canonical_profile_key": str(canonical["clinic_key"]),
                "source_profile_count": len(group),
                "outcome_profile_count": int(group["outcome_profile_included"].map(_boolean).sum()),
                "current_competitor_included": True,
                "historical_panel_retained": False,
                "coordinate_source": "business_listings_live",
                "evidence_url": "",
                "evidence_checked_at_utc": "",
                "manual_reason": "",
            }
        )
    discovered = pd.DataFrame.from_records(discovered_records)

    reference_flags = adjudicated_references.set_index("reference_key")
    carry_records: list[dict[str, Any]] = []
    for _, row in carry_forwards.iterrows():
        reference_key = str(row["reference_key"])
        reference = reference_flags.loc[reference_key]
        carry_records.append(
            {
                "competition_location_id": str(row["competition_location_id"]),
                "mapped_location": str(row["mapped_location"]),
                "title": row["title"],
                "address": row["address"],
                "zip": row["zip"],
                "phone": row["phone"],
                "domain": row["domain"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "location_source": "validated_legacy_carry_forward",
                "canonical_profile_key": reference_key,
                "source_profile_count": 1,
                "outcome_profile_count": 0,
                "current_competitor_included": True,
                "historical_panel_retained": _boolean(reference["historical_panel_included"]),
                "coordinate_source": row["coordinate_source"],
                "evidence_url": row["evidence_url"],
                "evidence_checked_at_utc": row["evidence_checked_at_utc"],
                "manual_reason": row["manual_reason"],
            }
        )
    carry = pd.DataFrame.from_records(carry_records, columns=discovered.columns)

    for _, carry_row in carry.iterrows():
        same_market = discovered.loc[
            discovered["mapped_location"].eq(carry_row["mapped_location"])
        ]
        normalized = normalize_name(carry_row["address"])
        if same_market["address"].map(normalize_name).eq(normalized).any():
            raise ValueError(
                f"Carry-forward address duplicates a discovered location: {carry_row['address']}"
            )
        distances = [
            distance
            for _, discovered_row in same_market.iterrows()
            if (distance := _distance_meters(carry_row, discovered_row)) is not None
        ]
        if distances and min(distances) <= 10:
            raise ValueError(
                "Carry-forward coordinates are within 10m of a discovered location: "
                f"{carry_row['competition_location_id']}"
            )

    locations = pd.concat([discovered, carry], ignore_index=True)
    if locations["competition_location_id"].duplicated().any():
        raise ValueError("Final competition_location_id values must be unique")
    locations = locations.sort_values(
        ["mapped_location", "location_source", "competition_location_id"]
    ).reset_index(drop=True)

    profile_crosswalk = joined[[
        "clinic_key",
        "competition_location_id",
        "is_canonical_competition_profile",
        "outcome_profile_included",
    ]].copy()
    profile_crosswalk = profile_crosswalk.rename(columns={"clinic_key": "source_profile_key"})
    profile_crosswalk["profile_source"] = "business_listings_live"
    profile_crosswalk["historical_panel_included"] = False
    profile_crosswalk["evidence_url"] = ""
    if len(carry):
        carry_profiles = pd.DataFrame({
            "source_profile_key": carry["canonical_profile_key"],
            "competition_location_id": carry["competition_location_id"],
            "is_canonical_competition_profile": True,
            "outcome_profile_included": False,
            "profile_source": "validated_legacy_carry_forward",
            "historical_panel_included": carry["historical_panel_retained"],
            "evidence_url": carry["evidence_url"],
        })
        profile_crosswalk = pd.concat([profile_crosswalk, carry_profiles], ignore_index=True)
    profile_crosswalk = profile_crosswalk.sort_values(
        ["competition_location_id", "source_profile_key"]
    ).reset_index(drop=True)

    market_counts = locations["mapped_location"].value_counts().sort_index()
    summary = {
        "analysis_status": "pilot_competition_universe_complete",
        "api_requests_submitted": 0,
        "business_listings_profiles": len(joined),
        "business_listings_discovered_locations": len(discovered),
        "validated_legacy_carry_forward_locations": len(carry),
        "final_competition_locations": len(locations),
        "final_competition_locations_by_market": {
            str(key): int(value) for key, value in market_counts.items()
        },
        "business_listings_outcome_profiles": int(
            joined["outcome_profile_included"].map(_boolean).sum()
        ),
        "carry_forward_new_outcome_profiles": 0,
        "carry_forward_historical_profiles_retained": int(
            carry["historical_panel_retained"].map(_boolean).sum()
        ) if len(carry) else 0,
        "duplicate_carry_forward_locations_detected": 0,
        "interpretation": (
            "Carry-forward locations enter current competition counts and retain eligible "
            "historical panels, but do not become newly discovered Business Listings outcomes."
        ),
    }
    return locations, profile_crosswalk, summary
