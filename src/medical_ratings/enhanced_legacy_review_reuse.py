"""Conservatively recover reusable legacy review histories after stage 47b."""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from medical_ratings.competition_units import normalize_full_address


DATE_COLUMNS = ("review_timestamp_utc", "review_date", "date")
RATING_COLUMNS = ("rating_value", "rating_numeric", "rating")
REVIEW_KEY_COLUMNS = ("review_id", "review_url")


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"nan", "none", "<na>"} else text


def _coalesce(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    result = pd.Series(pd.NA, index=frame.index, dtype="object")
    for column in columns:
        if column not in frame.columns:
            continue
        values = frame[column].map(_text)
        usable = result.isna() & values.ne("")
        result.loc[usable] = values.loc[usable]
    return result


def _phone(value: Any) -> str:
    return "".join(character for character in _text(value) if character.isdigit())[-10:]


def _domain(value: Any) -> str:
    text = _text(value).casefold()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = parsed.netloc.split("@")[-1].split(":")[0]
    return host.removeprefix("www.")


def _number(value: Any) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(number) else float(number)


def _distance_meters(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    values = [
        _number(left.get("latitude")),
        _number(left.get("longitude")),
        _number(right.get("latitude")),
        _number(right.get("longitude")),
    ]
    if any(value is None for value in values):
        return None
    lat1, lon1, lat2, lon2 = [math.radians(value) for value in values]
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(math.sqrt(min(1.0, haversine)))


def build_enhanced_legacy_review_reuse(
    manifest: pd.DataFrame,
    profiles: pd.DataFrame,
    existing_clinics: pd.DataFrame,
    existing_reviews: pd.DataFrame,
    stage47b_audit: pd.DataFrame,
    stage47b_reusable: pd.DataFrame,
    *,
    maximum_coordinate_distance_meters: float = 100.0,
    expected_manifest_rows: int | None = 29_550,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Return an enhanced reuse audit and a second reduced paid manifest.

    New automatic matches require a unique stage-47b market/title/ZIP candidate,
    an exact normalized full address, no conflicting phone/domain/coordinates,
    unique review IDs or review URLs, row-wise valid dates and ratings, and
    coverage of both old and current reported review counts.
    """

    if expected_manifest_rows is not None and len(manifest) != expected_manifest_rows:
        raise ValueError(
            f"Review manifest contains {len(manifest)} rows; expected {expected_manifest_rows}"
        )
    required_manifest = {
        "outcome_profile_key",
        "reported_votes_count",
        "estimated_maximum_cost_usd",
    }
    required_profiles = {"profile_key", "address"}
    required_clinics = {"clinic_key", "address"}
    required_audit = {
        "existing_clinic_key",
        "candidate_outcome_profile_key",
        "reuse_status",
        "existing_reported_reviews_count",
    }
    for frame, required, label in (
        (manifest, required_manifest, "manifest"),
        (profiles, required_profiles, "profiles"),
        (existing_clinics, required_clinics, "existing clinics"),
        (stage47b_audit, required_audit, "stage 47b audit"),
    ):
        missing = required - set(frame.columns)
        if missing:
            raise KeyError(f"{label} is missing columns: {sorted(missing)}")
    if "clinic_key" not in existing_reviews.columns:
        raise KeyError("Existing reviews are missing clinic_key")

    current = manifest.copy()
    current["outcome_profile_key"] = current["outcome_profile_key"].map(_text)
    if current["outcome_profile_key"].eq("").any() or current[
        "outcome_profile_key"
    ].duplicated().any():
        raise ValueError("Manifest outcome_profile_key must be unique and nonblank")
    profile_frame = profiles.copy()
    profile_frame["profile_key"] = profile_frame["profile_key"].map(_text)
    if profile_frame["profile_key"].duplicated().any():
        raise ValueError("Profiles contain duplicate profile_key values")
    profile_lookup = profile_frame.set_index("profile_key").to_dict(orient="index")

    clinics = existing_clinics.copy()
    clinics["clinic_key"] = clinics["clinic_key"].map(_text)
    if clinics["clinic_key"].duplicated().any():
        raise ValueError("Existing clinics contain duplicate clinic_key values")
    clinic_lookup = clinics.set_index("clinic_key").to_dict(orient="index")

    reviews = existing_reviews.copy()
    reviews["existing_clinic_key"] = reviews["clinic_key"].map(_text)
    reviews["_date"] = pd.to_datetime(
        _coalesce(reviews, DATE_COLUMNS), errors="coerce", utc=True
    )
    reviews["_rating"] = pd.to_numeric(
        _coalesce(reviews, RATING_COLUMNS), errors="coerce"
    )
    reviews["_review_key"] = _coalesce(reviews, REVIEW_KEY_COLUMNS).map(_text)
    stats = reviews.groupby("existing_clinic_key", sort=False).agg(
        review_rows=("existing_clinic_key", "size"),
        valid_dates=("_date", lambda values: int(values.notna().sum())),
        valid_ratings=("_rating", lambda values: int(values.between(1, 5).sum())),
        nonblank_review_keys=("_review_key", lambda values: int(values.ne("").sum())),
        unique_review_keys=("_review_key", lambda values: int(values[values.ne("")].nunique())),
        earliest_review_year=("_date", lambda values: values.dt.year.min()),
        latest_review_year=("_date", lambda values: values.dt.year.max()),
    ).reset_index()
    stats_lookup = stats.set_index("existing_clinic_key").to_dict(orient="index")
    current_reported = dict(
        zip(
            current["outcome_profile_key"],
            pd.to_numeric(current["reported_votes_count"], errors="coerce"),
            strict=True,
        )
    )

    candidate_status = "title_zip_candidate_not_auto_reused"
    candidates = stage47b_audit.loc[
        stage47b_audit["reuse_status"].eq(candidate_status)
    ].copy()
    rows: list[dict[str, Any]] = []
    for audit_row in candidates.to_dict(orient="records"):
        clinic_key = _text(audit_row["existing_clinic_key"])
        profile_key = _text(audit_row["candidate_outcome_profile_key"])
        old = clinic_lookup.get(clinic_key, {})
        new = profile_lookup.get(profile_key, {})
        old_address = normalize_full_address(old.get("address"))
        new_address = normalize_full_address(new.get("address"))
        same_address = bool(old_address and new_address and old_address == new_address)
        old_phone, new_phone = _phone(old.get("phone")), _phone(new.get("phone"))
        old_domain, new_domain = _domain(old.get("domain")), _domain(new.get("domain"))
        phone_conflict = bool(old_phone and new_phone and old_phone != new_phone)
        domain_conflict = bool(old_domain and new_domain and old_domain != new_domain)
        distance = _distance_meters(old, new)
        coordinate_conflict = bool(
            distance is not None and distance > maximum_coordinate_distance_meters
        )
        identity_approved = (
            bool(old)
            and bool(new)
            and same_address
            and not phone_conflict
            and not domain_conflict
            and not coordinate_conflict
        )

        review = stats_lookup.get(
            clinic_key,
            {
                "review_rows": 0,
                "valid_dates": 0,
                "valid_ratings": 0,
                "nonblank_review_keys": 0,
                "unique_review_keys": 0,
                "earliest_review_year": pd.NA,
                "latest_review_year": pd.NA,
            },
        )
        review_rows = int(review["review_rows"])
        old_reported = _number(audit_row.get("existing_reported_reviews_count"))
        new_reported = _number(current_reported.get(profile_key))
        coverage_target = (
            max(old_reported, new_reported)
            if old_reported is not None and new_reported is not None
            else None
        )
        review_rows_valid = (
            int(review["valid_dates"]) == review_rows
            and int(review["valid_ratings"]) == review_rows
            and int(review["nonblank_review_keys"]) == review_rows
            and int(review["unique_review_keys"]) == review_rows
        )
        coverage_complete = (
            coverage_target is not None
            and review_rows >= int(coverage_target)
            and review_rows_valid
        )
        zero_complete = (
            review_rows == 0 and old_reported == 0 and new_reported == 0
        )
        reusable = identity_approved and (coverage_complete or zero_complete)
        if reusable:
            status = "reuse_enhanced_exact_address_complete_history"
        elif not identity_approved:
            status = "enhanced_identity_not_approved"
        elif coverage_target is None:
            status = "enhanced_reported_count_missing"
        else:
            status = "enhanced_existing_history_incomplete"
        rows.append(
            {
                "existing_clinic_key": clinic_key,
                "candidate_outcome_profile_key": profile_key,
                "same_normalized_full_address": same_address,
                "phone_conflict": phone_conflict,
                "domain_conflict": domain_conflict,
                "coordinate_distance_meters": distance,
                "coordinate_conflict": coordinate_conflict,
                "enhanced_identity_approved": identity_approved,
                "existing_reported_reviews_count": old_reported,
                "current_reported_reviews_count": new_reported,
                "required_review_coverage_count": coverage_target,
                "existing_review_rows": review_rows,
                "valid_review_dates": int(review["valid_dates"]),
                "valid_review_ratings": int(review["valid_ratings"]),
                "nonblank_review_keys": int(review["nonblank_review_keys"]),
                "unique_review_keys": int(review["unique_review_keys"]),
                "earliest_review_year": review["earliest_review_year"],
                "latest_review_year": review["latest_review_year"],
                "enhanced_coverage_complete": bool(coverage_complete or zero_complete),
                "enhanced_reuse_status": status,
            }
        )

    enhanced_audit = pd.DataFrame.from_records(rows)
    reusable_status = "reuse_enhanced_exact_address_complete_history"
    enhanced_reusable = enhanced_audit.loc[
        enhanced_audit["enhanced_reuse_status"].eq(reusable_status)
    ].copy()
    prior_keys = set(
        stage47b_reusable.get(
            "candidate_outcome_profile_key", pd.Series(dtype="string")
        ).map(_text)
    )
    enhanced_keys = set(enhanced_reusable["candidate_outcome_profile_key"].map(_text))
    all_reusable_keys = prior_keys | enhanced_keys
    reduced_manifest = current.loc[
        ~current["outcome_profile_key"].isin(all_reusable_keys)
    ].copy()
    original_cost = float(
        pd.to_numeric(current["estimated_maximum_cost_usd"], errors="raise").sum()
    )
    reduced_cost = float(
        pd.to_numeric(
            reduced_manifest["estimated_maximum_cost_usd"], errors="raise"
        ).sum()
    )
    summary = {
        "analysis_status": "enhanced_legacy_review_reuse_audited",
        "api_requests_submitted": 0,
        "original_planned_tasks": int(len(current)),
        "stage47b_reusable_profiles": int(len(prior_keys)),
        "stage47b_title_zip_candidates": int(len(candidates)),
        "enhanced_identity_approved_profiles": int(
            enhanced_audit["enhanced_identity_approved"].sum()
        ),
        "new_enhanced_reusable_profiles": int(len(enhanced_keys - prior_keys)),
        "total_reusable_profiles": int(len(all_reusable_keys)),
        "remaining_paid_tasks": int(len(reduced_manifest)),
        "original_estimated_maximum_cost_usd": round(original_cost, 4),
        "enhanced_reduced_estimated_maximum_cost_usd": round(reduced_cost, 4),
        "estimated_maximum_cost_saved_usd": round(original_cost - reduced_cost, 4),
        "enhanced_reuse_status_counts": {
            str(key): int(value)
            for key, value in enhanced_audit["enhanced_reuse_status"]
            .value_counts()
            .sort_index()
            .items()
        },
        "identity_policy": (
            "New reuse requires the unique market/title/ZIP candidate from stage 47b, "
            "an exact normalized full address, no conflicting phone/domain/coordinates, "
            "unique review ID or URL coverage, valid row-wise coalesced dates and ratings, "
            "and coverage of both old and current reported counts."
        ),
    }
    return {
        "enhanced_audit": enhanced_audit.sort_values(
            ["enhanced_reuse_status", "existing_clinic_key"], ignore_index=True
        ),
        "enhanced_reusable": enhanced_reusable.sort_values(
            "candidate_outcome_profile_key", ignore_index=True
        ),
        "enhanced_reduced_manifest": reduced_manifest.reset_index(drop=True),
    }, summary
