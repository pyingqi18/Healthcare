"""Build corrected clinic and review tables from an audited batch replacement."""

from __future__ import annotations

from typing import Any

import pandas as pd

from medical_ratings.geography import normalize_location_code
from medical_ratings.identifiers import normalize_name, normalize_zip
from medical_ratings.replacement_audit import LEGACY_ERROR_BATCHES


CORRECT_LOCATION_CODES = {
    "Malone_NY_S": "1023114",
    "Syracuse_NY_M": "1023416",
}


def _affected_clinic_mask(clinics: pd.DataFrame) -> pd.Series:
    market = clinics["search_location"].astype("string").str.strip()
    code = clinics["used_location_code"].map(normalize_location_code)
    affected = pd.Series(False, index=clinics.index)
    for location, wrong_code in LEGACY_ERROR_BATCHES.items():
        affected |= market.eq(location) & code.eq(wrong_code)
    return affected


def _title_zip_key(title: pd.Series, postal: pd.Series) -> pd.Series:
    normalized_title = title.map(normalize_name).astype("string")
    normalized_zip = postal.map(normalize_zip).astype("string")
    complete = normalized_title.notna() & normalized_zip.notna()
    result = pd.Series(pd.NA, index=title.index, dtype="string")
    result.loc[complete] = (
        normalized_title.loc[complete] + "|" + normalized_zip.loc[complete]
    )
    return result


def prepare_corrected_locations(
    locations: pd.DataFrame,
    reviews: pd.DataFrame,
) -> pd.DataFrame:
    """Convert final physical locations to the prepared-clinic contract."""

    required_locations = {
        "final_physical_location_id",
        "clinic_key",
        "title",
        "zip",
        "latitude",
        "longitude",
        "mapped_location",
    }
    required_reviews = {
        "final_physical_location_id",
        "review_timestamp_utc",
    }
    missing_locations = required_locations - set(locations.columns)
    missing_reviews = required_reviews - set(reviews.columns)
    if missing_locations:
        raise KeyError(f"New locations are missing columns: {sorted(missing_locations)}")
    if missing_reviews:
        raise KeyError(f"New reviews are missing columns: {sorted(missing_reviews)}")

    result = locations.copy()
    result = result.rename(columns={"clinic_key": "canonical_profile_clinic_key"})
    result["clinic_key"] = result["final_physical_location_id"].astype("string")
    if result["clinic_key"].isna().any() or result["clinic_key"].duplicated().any():
        raise ValueError("Corrected physical location IDs must be present and unique")
    result["search_location"] = result["mapped_location"].astype("string")
    result["used_location_code"] = result["search_location"].map(
        CORRECT_LOCATION_CODES
    )
    if result["used_location_code"].isna().any():
        raise ValueError("Corrected locations contain an unsupported market")

    result["normalized_title"] = result["title"].map(normalize_name).astype("string")
    result["normalized_zip"] = result["zip"].map(normalize_zip).astype("string")
    result["title_zip_key"] = _title_zip_key(result["title"], result["zip"])
    if result["title_zip_key"].dropna().duplicated().any():
        raise ValueError("Corrected locations contain duplicate title and ZIP keys")

    review_dates = pd.to_datetime(
        reviews["review_timestamp_utc"], errors="coerce", utc=True
    )
    if review_dates.isna().any():
        raise ValueError("Corrected reviews contain invalid timestamps")
    earliest = (
        pd.DataFrame(
            {
                "final_physical_location_id": reviews[
                    "final_physical_location_id"
                ].astype("string"),
                "review_date": review_dates,
            }
        )
        .groupby("final_physical_location_id")["review_date"]
        .min()
    )
    result["earliest_review_date_parsed"] = result["clinic_key"].map(earliest)
    result["earliest_review_date"] = result["earliest_review_date_parsed"]
    result["timeline_match_method"] = "not_checked_for_rescrape"
    result["website_founded_year_raw"] = pd.NA
    result["website_founded_year"] = pd.Series(
        pd.NA, index=result.index, dtype="Int64"
    )
    result["website_founded_date_proxy"] = pd.NaT
    result["entry_date_proxy"] = result["earliest_review_date_parsed"]
    result["entry_date_source"] = result["entry_date_proxy"].notna().map(
        {True: "first_review", False: "missing"}
    )
    result["replacement_source"] = "corrected_location_rescrape"
    return result


def prepare_corrected_reviews(
    reviews: pd.DataFrame,
    locations: pd.DataFrame,
) -> pd.DataFrame:
    """Convert parsed reviews to the prepared-review contract."""

    required_reviews = {
        "clinic_key",
        "final_physical_location_id",
        "review_id",
        "review_timestamp_utc",
        "rating_value",
    }
    required_locations = {
        "final_physical_location_id",
        "title",
        "zip",
    }
    missing_reviews = required_reviews - set(reviews.columns)
    missing_locations = required_locations - set(locations.columns)
    if missing_reviews:
        raise KeyError(f"New reviews are missing columns: {sorted(missing_reviews)}")
    if missing_locations:
        raise KeyError(f"New locations are missing columns: {sorted(missing_locations)}")

    result = reviews.copy()
    result = result.rename(columns={"clinic_key": "source_profile_clinic_key"})
    result["clinic_key"] = result["final_physical_location_id"].astype("string")
    location_lookup = locations.set_index("final_physical_location_id")
    result["shop_title"] = result["final_physical_location_id"].map(
        location_lookup["title"]
    )
    result["shop_zip"] = result["final_physical_location_id"].map(
        location_lookup["zip"]
    )
    if result[["shop_title", "shop_zip"]].isna().any().any():
        raise ValueError("Corrected reviews could not be mapped to location title and ZIP")

    result["normalized_shop_title"] = result["shop_title"].map(normalize_name)
    result["normalized_shop_zip"] = result["shop_zip"].map(normalize_zip)
    result["review_title_zip_key"] = _title_zip_key(
        result["shop_title"], result["shop_zip"]
    )
    result["date"] = result["review_timestamp_utc"]
    result["review_date"] = pd.to_datetime(
        result["review_timestamp_utc"], errors="coerce", utc=True
    )
    result["rating"] = pd.to_numeric(result["rating_value"], errors="coerce")
    result["rating_numeric"] = result["rating"]
    if result["review_date"].isna().any():
        raise ValueError("Corrected reviews contain invalid review dates")
    if (~result["rating_numeric"].between(1, 5)).any():
        raise ValueError("Corrected reviews contain invalid ratings")
    result["non_us_postal_code"] = False
    result["zip_mismatch_with_unique_title"] = False
    result["review_linkage_method"] = "final_physical_location_id"
    result["review_linkage_status"] = "matched"
    result["replacement_source"] = "corrected_location_rescrape"
    return result


def build_corrected_tables(
    legacy_clinics: pd.DataFrame,
    legacy_reviews: pd.DataFrame,
    new_locations: pd.DataFrame,
    new_reviews: pd.DataFrame,
    zero_review_locations: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Remove the two wrong batches and append corrected physical locations."""

    affected_clinic = _affected_clinic_mask(legacy_clinics)
    affected_keys = set(legacy_clinics.loc[affected_clinic, "clinic_key"])
    affected_review = legacy_reviews["clinic_key"].isin(affected_keys)
    kept_clinics = legacy_clinics.loc[~affected_clinic].copy()
    kept_reviews = legacy_reviews.loc[~affected_review].copy()

    corrected_locations = prepare_corrected_locations(new_locations, new_reviews)
    corrected_reviews = prepare_corrected_reviews(new_reviews, new_locations)
    corrected_clinics = pd.concat(
        [kept_clinics, corrected_locations], ignore_index=True, sort=False
    )
    corrected_review_table = pd.concat(
        [kept_reviews, corrected_reviews], ignore_index=True, sort=False
    )

    if corrected_clinics["clinic_key"].isna().any():
        raise ValueError("Corrected clinic table contains missing clinic keys")
    if corrected_clinics["clinic_key"].duplicated().any():
        raise ValueError("Corrected clinic table contains duplicate clinic keys")
    known_keys = set(corrected_clinics["clinic_key"])
    unknown_review_keys = ~corrected_review_table["clinic_key"].isin(known_keys)
    if unknown_review_keys.any():
        raise ValueError(
            "Corrected review table contains unknown clinic keys: "
            f"{int(unknown_review_keys.sum())}"
        )

    new_location_ids = set(
        new_locations["final_physical_location_id"].astype("string")
    )
    zero_ids = set(
        zero_review_locations["final_physical_location_id"].astype("string")
    )
    new_review_location_ids = set(
        new_reviews["final_physical_location_id"].astype("string")
    )
    if new_review_location_ids & zero_ids:
        raise ValueError("A corrected location has both reviews and zero-review status")
    if new_review_location_ids | zero_ids != new_location_ids:
        raise ValueError("Corrected locations do not have complete review coverage")

    summary: dict[str, Any] = {
        "legacy_clinics_removed": int(affected_clinic.sum()),
        "legacy_reviews_removed": int(affected_review.sum()),
        "new_physical_locations_added": int(len(corrected_locations)),
        "new_reviews_added": int(len(corrected_reviews)),
        "zero_review_locations_preserved": int(len(zero_ids)),
        "new_locations_missing_entry_date": int(
            corrected_locations["entry_date_proxy"].isna().sum()
        ),
        "output_clinic_rows": int(len(corrected_clinics)),
        "unique_output_clinic_keys": int(corrected_clinics["clinic_key"].nunique()),
        "output_review_rows": int(len(corrected_review_table)),
        "output_reviews_with_known_clinic_key": int(
            corrected_review_table["clinic_key"].isin(known_keys).sum()
        ),
    }
    return corrected_clinics, corrected_review_table, summary
