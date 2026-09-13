"""Audit a location-code batch replacement before changing processed data."""

from __future__ import annotations

from typing import Any

import pandas as pd

from medical_ratings.geography import normalize_location_code
from medical_ratings.identifiers import normalize_name, normalize_zip


LEGACY_ERROR_BATCHES = {
    "Malone_NY_S": "1026588",
    "Syracuse_NY_M": "1027001",
}

EXPECTED_REPLACEMENT_COUNTS: dict[str, Any] = {
    "legacy_input_clinics": 5778,
    "legacy_input_reviews": 769515,
    "legacy_clinics_to_remove": 213,
    "legacy_reviews_to_remove": 22818,
    "new_physical_locations": 109,
    "new_review_rows": 14310,
    "new_zero_review_locations": 28,
    "new_locations_with_reviews": 81,
    "new_locations_by_market": {
        "Malone_NY_S": 8,
        "Syracuse_NY_M": 101,
    },
    "new_review_rows_by_market": {
        "Malone_NY_S": 542,
        "Syracuse_NY_M": 13768,
    },
    "zero_review_locations_by_market": {
        "Malone_NY_S": 2,
        "Syracuse_NY_M": 26,
    },
}


def _require_columns(
    frame: pd.DataFrame,
    required: set[str],
    label: str,
) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise KeyError(f"{label} is missing columns: {sorted(missing)}")


def _clean_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def _require_unique_nonblank(
    frame: pd.DataFrame,
    column: str,
    label: str,
) -> pd.Series:
    values = _clean_text(frame[column])
    if values.isna().any() or values.eq("").any():
        raise ValueError(f"{label} contains blank {column} values")
    if values.duplicated().any():
        raise ValueError(f"{label} contains duplicate {column} values")
    return values


def _count_strings(series: pd.Series) -> dict[str, int]:
    counts = series.astype("string").value_counts(dropna=False).sort_index()
    return {str(key): int(value) for key, value in counts.items()}


def _identity_key(title: pd.Series, postal: pd.Series) -> pd.Series:
    normalized_title = title.map(normalize_name).astype("string")
    normalized_zip = postal.map(normalize_zip).astype("string")
    complete = normalized_title.notna() & normalized_zip.notna()
    key = pd.Series(pd.NA, index=title.index, dtype="string")
    key.loc[complete] = (
        normalized_title.loc[complete] + "|" + normalized_zip.loc[complete]
    )
    return key


def _build_collision_review(
    unaffected_legacy: pd.DataFrame,
    new_locations: pd.DataFrame,
) -> pd.DataFrame:
    legacy = unaffected_legacy.copy()
    new = new_locations.copy()
    legacy["identity_key"] = _identity_key(legacy["title"], legacy["zip"])
    new["identity_key"] = _identity_key(new["title"], new["zip"])
    legacy = legacy.dropna(subset=["identity_key"])
    new = new.dropna(subset=["identity_key"])
    collisions = new.merge(
        legacy,
        on="identity_key",
        how="inner",
        suffixes=("_new", "_legacy"),
        validate="many_to_many",
    )
    columns = [
        "identity_key",
        "final_physical_location_id",
        "clinic_key_new",
        "title_new",
        "zip_new",
        "mapped_location",
        "clinic_key_legacy",
        "title_legacy",
        "zip_legacy",
        "search_location",
    ]
    if collisions.empty:
        return pd.DataFrame(columns=columns)
    return (
        collisions[columns]
        .sort_values(
            ["mapped_location", "title_new", "clinic_key_legacy"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def audit_replacement_inputs(
    legacy_clinics: pd.DataFrame,
    legacy_reviews: pd.DataFrame,
    new_locations: pd.DataFrame,
    new_reviews: pd.DataFrame,
    zero_review_locations: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return batch counts, possible collisions, and a readiness summary."""

    _require_columns(
        legacy_clinics,
        {"clinic_key", "title", "zip", "search_location", "used_location_code"},
        "legacy clinics",
    )
    _require_columns(legacy_reviews, {"clinic_key"}, "legacy reviews")
    _require_columns(
        new_locations,
        {
            "final_physical_location_id",
            "clinic_key",
            "title",
            "zip",
            "mapped_location",
        },
        "new locations",
    )
    _require_columns(
        new_reviews,
        {
            "final_physical_location_id",
            "review_id",
            "review_timestamp_utc",
            "rating_value",
            "requested_location",
        },
        "new reviews",
    )
    _require_columns(
        zero_review_locations,
        {"final_physical_location_id", "requested_location"},
        "zero-review locations",
    )

    legacy_keys = _require_unique_nonblank(
        legacy_clinics, "clinic_key", "legacy clinics"
    )
    location_ids = _require_unique_nonblank(
        new_locations, "final_physical_location_id", "new locations"
    )
    _require_unique_nonblank(new_locations, "clinic_key", "new locations")
    review_ids = _require_unique_nonblank(new_reviews, "review_id", "new reviews")
    zero_ids = _require_unique_nonblank(
        zero_review_locations,
        "final_physical_location_id",
        "zero-review locations",
    )

    legacy_review_keys = _clean_text(legacy_reviews["clinic_key"])
    unknown_legacy_review_keys = ~legacy_review_keys.isin(set(legacy_keys))
    if unknown_legacy_review_keys.any():
        raise ValueError(
            "Legacy reviews contain unknown clinic_key values: "
            f"{int(unknown_legacy_review_keys.sum())}"
        )

    legacy_market = _clean_text(legacy_clinics["search_location"])
    legacy_code = legacy_clinics["used_location_code"].map(
        normalize_location_code
    )
    affected_mask = pd.Series(False, index=legacy_clinics.index)
    batch_records: list[dict[str, Any]] = []
    for market, wrong_code in LEGACY_ERROR_BATCHES.items():
        batch_mask = legacy_market.eq(market) & legacy_code.eq(wrong_code)
        batch_keys = set(legacy_keys.loc[batch_mask])
        batch_review_rows = int(legacy_review_keys.isin(batch_keys).sum())
        affected_mask |= batch_mask
        batch_records.append(
            {
                "search_location": market,
                "wrong_location_code": wrong_code,
                "legacy_clinics_to_remove": int(batch_mask.sum()),
                "legacy_reviews_to_remove": batch_review_rows,
            }
        )

    wrong_code_mask = legacy_code.isin(set(LEGACY_ERROR_BATCHES.values()))
    if (wrong_code_mask & ~affected_mask).any():
        raise ValueError("A known wrong location code appears outside its expected market")

    affected_keys = set(legacy_keys.loc[affected_mask])
    affected_review_mask = legacy_review_keys.isin(affected_keys)
    batch_audit = pd.DataFrame.from_records(batch_records)

    new_market = _clean_text(new_locations["mapped_location"])
    allowed_markets = set(LEGACY_ERROR_BATCHES)
    unexpected_markets = set(new_market.dropna()) - allowed_markets
    if unexpected_markets:
        raise ValueError(
            f"New locations contain unexpected markets: {sorted(unexpected_markets)}"
        )

    known_location_ids = set(location_ids)
    review_location_ids = _clean_text(new_reviews["final_physical_location_id"])
    unknown_review_locations = ~review_location_ids.isin(known_location_ids)
    if unknown_review_locations.any():
        raise ValueError(
            "New reviews contain unknown final location IDs: "
            f"{int(unknown_review_locations.sum())}"
        )
    unknown_zero_locations = ~zero_ids.isin(known_location_ids)
    if unknown_zero_locations.any():
        raise ValueError("Zero-review rows contain unknown final location IDs")

    locations_with_reviews = set(review_location_ids)
    zero_location_set = set(zero_ids)
    overlap = locations_with_reviews & zero_location_set
    if overlap:
        raise ValueError("Locations cannot have both parsed and zero-review status")
    covered_locations = locations_with_reviews | zero_location_set
    missing_location_status = known_location_ids - covered_locations
    if missing_location_status:
        raise ValueError(
            "New locations are missing review observation status: "
            f"{len(missing_location_status)}"
        )

    location_market_map = dict(zip(location_ids, new_market, strict=True))
    expected_review_market = review_location_ids.map(location_market_map)
    observed_review_market = _clean_text(new_reviews["requested_location"])
    if not expected_review_market.eq(observed_review_market).all():
        raise ValueError("New review market does not match final location market")
    expected_zero_market = zero_ids.map(location_market_map)
    observed_zero_market = _clean_text(zero_review_locations["requested_location"])
    if not expected_zero_market.eq(observed_zero_market).all():
        raise ValueError("Zero-review market does not match final location market")

    timestamps = pd.to_datetime(
        new_reviews["review_timestamp_utc"], errors="coerce", utc=True
    )
    if timestamps.isna().any():
        raise ValueError("New reviews contain invalid timestamps")
    ratings = pd.to_numeric(new_reviews["rating_value"], errors="coerce")
    invalid_rating = ratings.isna() | ~ratings.between(1, 5)
    if invalid_rating.any():
        raise ValueError("New reviews contain invalid ratings")

    unaffected_legacy = legacy_clinics.loc[~affected_mask].copy()
    collisions = _build_collision_review(unaffected_legacy, new_locations)
    years = timestamps.dt.year
    legacy_review_id_available = "review_id" in legacy_reviews.columns
    cross_source_review_id_collisions = 0
    if legacy_review_id_available:
        old_review_ids = set(
            _clean_text(legacy_reviews.loc[~affected_review_mask, "review_id"])
            .dropna()
            .loc[lambda values: values.ne("")]
        )
        cross_source_review_id_collisions = int(review_ids.isin(old_review_ids).sum())

    summary: dict[str, Any] = {
        "legacy_input_clinics": int(len(legacy_clinics)),
        "legacy_input_reviews": int(len(legacy_reviews)),
        "legacy_clinics_to_remove": int(affected_mask.sum()),
        "legacy_reviews_to_remove": int(affected_review_mask.sum()),
        "new_physical_locations": int(len(new_locations)),
        "new_review_rows": int(len(new_reviews)),
        "new_zero_review_locations": int(len(zero_review_locations)),
        "new_locations_with_reviews": int(len(locations_with_reviews)),
        "new_locations_by_market": _count_strings(new_market),
        "new_review_rows_by_market": _count_strings(observed_review_market),
        "zero_review_locations_by_market": _count_strings(observed_zero_market),
        "unique_new_review_id": int(review_ids.nunique()),
        "new_reviews_through_2025": int(years.le(2025).sum()),
        "new_reviews_after_2025": int(years.gt(2025).sum()),
        "legacy_review_id_available": bool(legacy_review_id_available),
        "cross_source_review_id_collisions": cross_source_review_id_collisions,
        "potential_unaffected_legacy_location_collisions": int(len(collisions)),
        "projected_clinic_rows": int(
            len(legacy_clinics) - affected_mask.sum() + len(new_locations)
        ),
        "projected_review_rows": int(
            len(legacy_reviews) - affected_review_mask.sum() + len(new_reviews)
        ),
        "replacement_ready": bool(
            collisions.empty and cross_source_review_id_collisions == 0
        ),
    }
    return batch_audit, collisions, summary


def validate_expected_replacement_counts(
    summary: dict[str, Any],
    expected: dict[str, Any] = EXPECTED_REPLACEMENT_COUNTS,
) -> None:
    """Reject any change from the frozen repair-batch counts."""

    mismatches = {
        key: {"expected": value, "observed": summary.get(key)}
        for key, value in expected.items()
        if summary.get(key) != value
    }
    if mismatches:
        raise ValueError(f"Replacement counts changed: {mismatches}")
