"""Audit reusable corrected-v1 review histories before new paid collection."""

from __future__ import annotations

from typing import Any

import pandas as pd

from medical_ratings.identifiers import normalize_name, normalize_zip


STABLE_KEY_COLUMNS = (
    "canonical_profile_clinic_key",
    "source_profile_clinic_key",
    "profile_key",
)
REPORTED_COUNT_COLUMNS = (
    "votes_count",
    "reviews_count",
    "review_count",
    "vote_count",
)
DATE_COLUMNS = ("review_timestamp_utc", "review_date", "date")
RATING_COLUMNS = ("rating_value", "rating_numeric", "rating")
REVIEW_ID_COLUMNS = ("review_id", "id")


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _first_present(frame: pd.DataFrame, columns: tuple[str, ...]) -> str | None:
    return next((column for column in columns if column in frame.columns), None)


def _profile_zip(frame: pd.DataFrame) -> pd.Series:
    if "zip" in frame.columns:
        return frame["zip"].map(normalize_zip).astype("string")
    address = frame.get("address", pd.Series("", index=frame.index)).astype("string")
    extracted = address.str.extract(r"\b(\d{5})(?:-\d{4})?\b", expand=False)
    return extracted.map(normalize_zip).astype("string")


def _title_zip_key(title: pd.Series, postal: pd.Series) -> pd.Series:
    normalized_title = title.map(normalize_name).astype("string")
    normalized_zip = postal.map(normalize_zip).astype("string")
    complete = normalized_title.notna() & normalized_zip.notna()
    result = pd.Series(pd.NA, index=title.index, dtype="string")
    result.loc[complete] = (
        normalized_title.loc[complete] + "|" + normalized_zip.loc[complete]
    )
    return result


def _as_number(value: Any) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(number) else float(number)


def build_existing_review_reuse_audit(
    manifest: pd.DataFrame,
    profiles: pd.DataFrame,
    existing_clinics: pd.DataFrame,
    existing_reviews: pd.DataFrame,
    *,
    analysis_end_year: int = 2025,
    expected_manifest_rows: int | None = 29_550,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Return conservative reuse decisions and a reduced paid manifest.

    Automatic reuse requires a stable Google identifier and complete existing
    review coverage against the existing clinic's reported review count.
    Title and ZIP matches are exported as candidates but never auto-reused.
    """

    manifest_required = {
        "outcome_profile_key",
        "clinic_key",
        "cid",
        "place_id",
        "requested_location",
        "reported_votes_count",
        "planned_depth",
        "estimated_maximum_cost_usd",
    }
    missing = manifest_required - set(manifest.columns)
    if missing:
        raise KeyError(f"Review manifest is missing columns: {sorted(missing)}")
    profile_required = {"clinic_key", "profile_key", "cid", "title"}
    missing = profile_required - set(profiles.columns)
    if missing:
        raise KeyError(f"Outcome profiles are missing columns: {sorted(missing)}")
    clinic_required = {"clinic_key", "title"}
    missing = clinic_required - set(existing_clinics.columns)
    if missing:
        raise KeyError(f"Existing clinics are missing columns: {sorted(missing)}")
    if "clinic_key" not in existing_reviews.columns:
        raise KeyError("Existing reviews are missing clinic_key")
    if expected_manifest_rows is not None and len(manifest) != expected_manifest_rows:
        raise ValueError(
            f"Review manifest contains {len(manifest)} rows; "
            f"expected {expected_manifest_rows}"
        )

    current = manifest.copy()
    for column in ("outcome_profile_key", "clinic_key", "cid", "place_id"):
        current[column] = current[column].map(_text)
        if current[column].eq("").any() or current[column].duplicated().any():
            raise ValueError(f"Manifest requires unique nonblank {column}")
    profile_frame = profiles.copy()
    for column in ("clinic_key", "profile_key", "cid"):
        profile_frame[column] = profile_frame[column].map(_text)
    if profile_frame["clinic_key"].duplicated().any():
        raise ValueError("Outcome profiles contain duplicate clinic_key values")
    if set(profile_frame["clinic_key"]) != set(current["clinic_key"]):
        raise ValueError("Outcome profiles do not exactly cover the review manifest")

    profile_context = profile_frame.copy()
    profile_context["current_zip"] = _profile_zip(profile_context)
    profile_context["current_title_zip_key"] = _title_zip_key(
        profile_context["title"], profile_context["current_zip"]
    )
    market_column = (
        "requested_location"
        if "requested_location" in profile_context.columns
        else "mapped_location"
    )
    if market_column not in profile_context.columns:
        raise KeyError("Outcome profiles lack requested_location or mapped_location")
    profile_context["current_market"] = profile_context[market_column].map(_text)
    current_context = current.merge(
        profile_context[
            ["clinic_key", "current_zip", "current_title_zip_key", "current_market"]
        ],
        on="clinic_key",
        how="left",
        validate="one_to_one",
    )

    outcome_keys = set(current["outcome_profile_key"])
    cid_map = dict(zip(current["cid"], current["outcome_profile_key"], strict=True))
    place_map = dict(
        zip(current["place_id"], current["outcome_profile_key"], strict=True)
    )
    current_title_zip = current_context.dropna(
        subset=["current_title_zip_key"]
    ).copy()
    unique_current_title_zip = (
        current_title_zip.groupby(["requested_location", "current_title_zip_key"])[
            "outcome_profile_key"
        ]
        .agg(lambda values: sorted(set(values)))
        .to_dict()
    )

    clinics = existing_clinics.copy()
    clinics["existing_clinic_key"] = clinics["clinic_key"].map(_text)
    if clinics["existing_clinic_key"].eq("").any():
        raise ValueError("Existing clinics contain blank clinic_key values")
    if clinics["existing_clinic_key"].duplicated().any():
        raise ValueError("Existing clinics contain duplicate clinic_key values")
    clinics["existing_market"] = clinics.get(
        "search_location", pd.Series("", index=clinics.index)
    ).map(_text)
    existing_zip = (
        clinics["zip"]
        if "zip" in clinics.columns
        else pd.Series(pd.NA, index=clinics.index)
    )
    clinics["existing_title_zip_key"] = _title_zip_key(
        clinics["title"], existing_zip
    )
    reported_column = _first_present(clinics, REPORTED_COUNT_COLUMNS)
    clinics["existing_reported_reviews_count"] = (
        pd.to_numeric(clinics[reported_column], errors="coerce")
        if reported_column is not None
        else pd.Series(float("nan"), index=clinics.index)
    )

    date_column = _first_present(existing_reviews, DATE_COLUMNS)
    rating_column = _first_present(existing_reviews, RATING_COLUMNS)
    review_id_column = _first_present(existing_reviews, REVIEW_ID_COLUMNS)
    if date_column is None or rating_column is None or review_id_column is None:
        raise KeyError(
            "Existing reviews lack a recognized date, rating, or review ID column"
        )
    reviews = existing_reviews.copy()
    reviews["existing_clinic_key"] = reviews["clinic_key"].map(_text)
    timestamps = pd.to_datetime(reviews[date_column], errors="coerce", utc=True)
    ratings = pd.to_numeric(reviews[rating_column], errors="coerce")
    reviews["_valid_date"] = timestamps.notna()
    reviews["_valid_rating"] = ratings.between(1, 5)
    reviews["_review_year"] = timestamps.dt.year
    reviews["_review_id"] = reviews[review_id_column].map(_text)
    reviews["_stable_review_profile_key"] = ""
    for column in STABLE_KEY_COLUMNS:
        if column not in reviews.columns:
            continue
        values = reviews[column].map(_text)
        usable = reviews["_stable_review_profile_key"].eq("") & values.isin(outcome_keys)
        reviews.loc[usable, "_stable_review_profile_key"] = values.loc[usable]
    review_stats = reviews.groupby("existing_clinic_key", sort=False).agg(
        existing_review_rows=("existing_clinic_key", "size"),
        valid_existing_review_dates=("_valid_date", "sum"),
        valid_existing_review_ratings=("_valid_rating", "sum"),
        existing_reviews_through_analysis_end=(
            "_review_year", lambda values: int(values.le(analysis_end_year).sum())
        ),
        existing_earliest_review_year=("_review_year", "min"),
        existing_latest_review_year=("_review_year", "max"),
        nonblank_review_ids=("_review_id", lambda values: int(values.ne("").sum())),
        unique_review_ids=("_review_id", lambda values: int(values[values.ne("")].nunique())),
        stable_review_profile_keys=(
            "_stable_review_profile_key",
            lambda values: "|".join(sorted(set(values[values.ne("")]))),
        ),
        reviews_with_stable_profile_identity=(
            "_stable_review_profile_key", lambda values: int(values.ne("").sum())
        ),
    ).reset_index()
    clinics = clinics.merge(
        review_stats,
        on="existing_clinic_key",
        how="left",
        validate="one_to_one",
    )
    for column in (
        "existing_review_rows",
        "valid_existing_review_dates",
        "valid_existing_review_ratings",
        "existing_reviews_through_analysis_end",
        "nonblank_review_ids",
        "unique_review_ids",
        "reviews_with_stable_profile_identity",
    ):
        clinics[column] = pd.to_numeric(clinics[column], errors="coerce").fillna(0).astype(int)
    clinics["stable_review_profile_keys"] = clinics[
        "stable_review_profile_keys"
    ].fillna("").astype("string")

    current_reported = dict(
        zip(
            current["outcome_profile_key"],
            pd.to_numeric(current["reported_votes_count"], errors="coerce"),
            strict=True,
        )
    )

    mapping_rows: list[dict[str, Any]] = []
    for row in clinics.to_dict(orient="records"):
        stable_matches: set[str] = set()
        stable_evidence: list[str] = []
        for column in STABLE_KEY_COLUMNS:
            value = _text(row.get(column))
            if value in outcome_keys:
                stable_matches.add(value)
                stable_evidence.append(column)
        cid = _text(row.get("cid"))
        if cid in cid_map:
            stable_matches.add(cid_map[cid])
            stable_evidence.append("cid")
        place_id = _text(row.get("place_id"))
        if place_id in place_map:
            stable_matches.add(place_map[place_id])
            stable_evidence.append("place_id")
        clinic_key = _text(row.get("clinic_key"))
        if clinic_key in outcome_keys:
            stable_matches.add(clinic_key)
            stable_evidence.append("clinic_key")

        candidate_key = None
        candidate_method = "no_match"
        identity_conflict = len(stable_matches) > 1
        if len(stable_matches) == 1:
            candidate_key = next(iter(stable_matches))
            candidate_method = "stable_google_identifier"
        elif not stable_matches:
            title_zip = row.get("existing_title_zip_key")
            market = _text(row.get("existing_market"))
            candidates = unique_current_title_zip.get((market, title_zip), [])
            if len(candidates) == 1:
                candidate_key = candidates[0]
                candidate_method = "unique_market_title_zip_candidate"
            elif len(candidates) > 1:
                candidate_method = "ambiguous_market_title_zip"

        existing_reported = _as_number(row.get("existing_reported_reviews_count"))
        current_reported_count = (
            _as_number(current_reported.get(candidate_key))
            if candidate_key is not None
            else None
        )
        review_rows = int(row["existing_review_rows"])
        valid_rows = (
            int(row["valid_existing_review_dates"]) == review_rows
            and int(row["valid_existing_review_ratings"]) == review_rows
        )
        review_identity_complete = (
            int(row["reviews_with_stable_profile_identity"]) == review_rows
            and int(row["nonblank_review_ids"]) == review_rows
            and int(row["unique_review_ids"]) == review_rows
            and row["stable_review_profile_keys"] == candidate_key
        )
        coverage_target = (
            max(existing_reported, current_reported_count)
            if existing_reported is not None and current_reported_count is not None
            else None
        )
        nonzero_coverage_complete = (
            review_rows > 0
            and coverage_target is not None
            and coverage_target >= 0
            and review_rows >= int(coverage_target)
            and valid_rows
            and review_identity_complete
        )
        zero_coverage_complete = (
            review_rows == 0
            and current_reported_count == 0
            and existing_reported == 0
        )
        coverage_complete = nonzero_coverage_complete or zero_coverage_complete
        if identity_conflict:
            reuse_status = "conflicting_stable_identity"
        elif candidate_method == "stable_google_identifier" and coverage_complete:
            reuse_status = (
                "reuse_zero_review_profile"
                if zero_coverage_complete
                else "reuse_complete_existing_history"
            )
        elif candidate_method == "stable_google_identifier" and current_reported_count is None:
            reuse_status = "stable_match_current_reported_count_missing"
        elif candidate_method == "stable_google_identifier":
            reuse_status = "stable_match_existing_history_incomplete"
        elif candidate_method == "unique_market_title_zip_candidate":
            reuse_status = "title_zip_candidate_not_auto_reused"
        elif candidate_method == "ambiguous_market_title_zip":
            reuse_status = "ambiguous_title_zip_not_reused"
        else:
            reuse_status = "no_existing_profile_match"
        mapping_rows.append(
            {
                "existing_clinic_key": row["existing_clinic_key"],
                "candidate_outcome_profile_key": candidate_key,
                "identity_match_method": candidate_method,
                "stable_identity_evidence": "|".join(sorted(stable_evidence)),
                "existing_market": row["existing_market"],
                "existing_title": row["title"],
                "existing_title_zip_key": row["existing_title_zip_key"],
                "existing_reported_reviews_count": existing_reported,
                "current_reported_reviews_count": current_reported_count,
                "required_review_coverage_count": coverage_target,
                "existing_review_rows": review_rows,
                "valid_existing_review_dates": int(row["valid_existing_review_dates"]),
                "valid_existing_review_ratings": int(row["valid_existing_review_ratings"]),
                "existing_reviews_through_analysis_end": int(
                    row["existing_reviews_through_analysis_end"]
                ),
                "existing_earliest_review_year": row.get("existing_earliest_review_year"),
                "existing_latest_review_year": row.get("existing_latest_review_year"),
                "nonblank_review_ids": int(row["nonblank_review_ids"]),
                "unique_review_ids": int(row["unique_review_ids"]),
                "reviews_with_stable_profile_identity": int(
                    row["reviews_with_stable_profile_identity"]
                ),
                "stable_review_profile_keys": row["stable_review_profile_keys"],
                "review_identity_complete": review_identity_complete,
                "existing_coverage_complete": coverage_complete,
                "reuse_status": reuse_status,
            }
        )

    existing_audit = pd.DataFrame.from_records(mapping_rows)
    duplicate_candidate = existing_audit["candidate_outcome_profile_key"].notna() & (
        existing_audit["candidate_outcome_profile_key"].duplicated(keep=False)
    )
    existing_audit.loc[duplicate_candidate, "reuse_status"] = (
        "multiple_existing_clinics_map_to_profile_not_reused"
    )
    reusable_statuses = {
        "reuse_complete_existing_history",
        "reuse_zero_review_profile",
    }
    reusable_existing = existing_audit.loc[
        existing_audit["reuse_status"].isin(reusable_statuses)
    ].copy()
    reusable_keys = set(reusable_existing["candidate_outcome_profile_key"].dropna())
    reduced_manifest = current.loc[
        ~current["outcome_profile_key"].isin(reusable_keys)
    ].copy()
    reuse_candidates = existing_audit.loc[
        existing_audit["reuse_status"].isin(
            {
                "title_zip_candidate_not_auto_reused",
                "ambiguous_title_zip_not_reused",
                "stable_match_current_reported_count_missing",
                "stable_match_existing_history_incomplete",
                "multiple_existing_clinics_map_to_profile_not_reused",
            }
        )
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
        "analysis_status": "existing_review_reuse_audited",
        "api_requests_submitted": 0,
        "analysis_end_year": int(analysis_end_year),
        "existing_clinics": int(len(clinics)),
        "existing_review_rows": int(len(reviews)),
        "original_planned_tasks": int(len(current)),
        "stable_identifier_matches": int(
            existing_audit["identity_match_method"].eq("stable_google_identifier").sum()
        ),
        "title_zip_identity_candidates_not_auto_reused": int(
            existing_audit["identity_match_method"]
            .eq("unique_market_title_zip_candidate")
            .sum()
        ),
        "reusable_existing_profiles": int(len(reusable_keys)),
        "reusable_existing_review_rows": int(
            reusable_existing["existing_review_rows"].sum()
        ),
        "remaining_paid_tasks": int(len(reduced_manifest)),
        "tasks_removed_by_safe_reuse": int(len(current) - len(reduced_manifest)),
        "original_estimated_maximum_cost_usd": round(original_cost, 4),
        "reduced_estimated_maximum_cost_usd": round(reduced_cost, 4),
        "estimated_maximum_cost_saved_usd": round(original_cost - reduced_cost, 4),
        "reuse_status_counts": {
            str(key): int(value)
            for key, value in existing_audit["reuse_status"]
            .value_counts()
            .sort_index()
            .items()
        },
        "automatic_title_zip_reuse": 0,
        "identity_policy": (
            "Only stable Google identifiers with profile-level review provenance, "
            "unique review IDs, and coverage of both old and current reported counts are removed "
            "from the paid manifest. Title and ZIP are audit candidates only."
        ),
    }
    return {
        "existing_audit": existing_audit.sort_values(
            ["reuse_status", "existing_market", "existing_clinic_key"],
            ignore_index=True,
        ),
        "reusable_existing": reusable_existing.sort_values(
            ["existing_market", "candidate_outcome_profile_key"],
            ignore_index=True,
        ),
        "reuse_candidates": reuse_candidates.sort_values(
            ["reuse_status", "existing_market", "existing_clinic_key"],
            ignore_index=True,
        ),
        "reduced_manifest": reduced_manifest.reset_index(drop=True),
    }, summary
