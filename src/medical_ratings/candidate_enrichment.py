"""Merge exact-CID Business Info profiles into clinic-search candidates."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

import pandas as pd

from medical_ratings.candidate_audit import _zip_market_lookup
from medical_ratings.identifiers import normalize_zip


REQUIRED_CANDIDATE_COLUMNS = {
    "clinic_key",
    "cid",
    "place_id",
    "title",
    "category",
    "address",
    "zip",
    "latitude",
    "longitude",
    "phone",
    "domain",
    "url",
    "rating_value",
    "votes_count",
    "result_datetime_utc",
    "requested_locations",
    "market_assignment_status",
    "eligibility_review_status",
}
REQUIRED_PROFILE_COLUMNS = {
    "cid",
    "place_id",
    "title",
    "category",
    "address",
    "zip",
    "country_code",
    "latitude",
    "longitude",
    "phone",
    "domain",
    "url",
    "rating_value",
    "votes_count",
    "result_datetime_utc",
}
RESOLVED_FIELDS = (
    "place_id",
    "title",
    "category",
    "address",
    "latitude",
    "longitude",
    "phone",
    "domain",
    "url",
    "rating_value",
    "votes_count",
    "result_datetime_utc",
)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return not isinstance(value, str) or bool(value.strip())


def _preferred(primary: Any, fallback: Any) -> Any:
    return primary if _has_value(primary) else fallback


def _address_zip(address: Any, country_code: Any) -> str | None:
    if not _has_value(address):
        return None
    if _has_value(country_code) and str(country_code).strip().upper() != "US":
        return None
    match = re.search(r"(?<!\d)(\d{5})(?:-\d{4})?(?!\d)", str(address))
    return None if match is None else match.group(1)


def enrich_candidates_with_business_info(
    candidates: pd.DataFrame,
    profiles: pd.DataFrame,
    regions: Mapping[str, Mapping[str, Any]],
) -> pd.DataFrame:
    """Return all candidates with resolved fields and recomputed geography."""

    missing_candidates = REQUIRED_CANDIDATE_COLUMNS - set(candidates.columns)
    if missing_candidates:
        raise KeyError(
            f"Candidates are missing columns: {sorted(missing_candidates)}"
        )
    missing_profiles = REQUIRED_PROFILE_COLUMNS - set(profiles.columns)
    if missing_profiles:
        raise KeyError(f"Profiles are missing columns: {sorted(missing_profiles)}")
    if candidates.empty or profiles.empty:
        raise ValueError("Candidates and profiles must both be non-empty")

    candidate_frame = candidates.copy()
    profile_frame = profiles.copy()
    candidate_frame["cid"] = candidate_frame["cid"].astype("string").str.strip()
    profile_frame["cid"] = profile_frame["cid"].astype("string").str.strip()
    if candidate_frame["cid"].duplicated().any():
        raise ValueError("Candidates contain duplicate CID values")
    if profile_frame["cid"].duplicated().any():
        raise ValueError("Business Info profiles contain duplicate CID values")

    expected_profile_cids = set(
        candidate_frame.loc[
            candidate_frame["eligibility_review_status"].eq("needs_geography"),
            "cid",
        ]
    )
    observed_profile_cids = set(profile_frame["cid"])
    if observed_profile_cids != expected_profile_cids:
        missing = sorted(expected_profile_cids - observed_profile_cids)[:5]
        unexpected = sorted(observed_profile_cids - expected_profile_cids)[:5]
        raise ValueError(
            "Business Info profile CID coverage does not match needs_geography "
            f"candidates; missing={missing}, unexpected={unexpected}"
        )

    candidate_frame = candidate_frame.rename(
        columns={field: f"search_{field}" for field in (*RESOLVED_FIELDS, "zip")}
    )
    profile_frame = profile_frame.rename(
        columns={
            column: f"business_info_{column}"
            for column in profile_frame.columns
            if column != "cid"
        }
    )
    merged = candidate_frame.merge(
        profile_frame,
        on="cid",
        how="left",
        validate="one_to_one",
    )
    merged["business_info_matched"] = merged["business_info_task_id"].notna()

    for field in RESOLVED_FIELDS:
        merged[field] = [
            _preferred(primary, fallback)
            for primary, fallback in zip(
                merged[f"business_info_{field}"],
                merged[f"search_{field}"],
                strict=True,
            )
        ]

    resolved_zips: list[str | None] = []
    for _, row in merged.iterrows():
        profile_zip = normalize_zip(row.get("business_info_zip"))
        fallback_address_zip = _address_zip(
            row.get("business_info_address"),
            row.get("business_info_country_code"),
        )
        search_zip = normalize_zip(row.get("search_zip"))
        resolved_zips.append(profile_zip or fallback_address_zip or search_zip)
    merged["zip"] = resolved_zips

    target_regions = {
        region
        for values in merged["requested_locations"].dropna().astype(str)
        for region in values.split("|")
    }
    zip_lookup = _zip_market_lookup(regions, target_regions)
    merged["mapped_location"] = merged["zip"].map(zip_lookup)

    statuses: list[str] = []
    for _, row in merged.iterrows():
        if _has_value(row.get("mapped_location")):
            statuses.append("eligible_target_zip")
        elif _has_value(row.get("zip")):
            statuses.append("outside_target_zip")
        elif (
            _has_value(row.get("business_info_country_code"))
            and str(row.get("business_info_country_code")).strip().upper() != "US"
        ):
            statuses.append("outside_target_zip")
        else:
            statuses.append("maps_missing_zip")
    merged["previous_market_assignment_status"] = merged[
        "market_assignment_status"
    ]
    merged["market_assignment_status"] = statuses
    merged["target_zip_eligible"] = merged["market_assignment_status"].eq(
        "eligible_target_zip"
    )
    return merged
