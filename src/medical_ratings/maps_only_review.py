"""Triage true Maps-only profiles and build cross-source identity review pairs."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import pandas as pd

from medical_ratings.duplicate_candidate_audit import (
    _distance_meters,
    _domain,
    _phone,
    _similarity,
)
from medical_ratings.identifiers import normalize_name
from medical_ratings.maps_supplement_audit import _as_boolean


STRONG_DENTAL_PROVIDER_TITLE = re.compile(
    r"(?:\bdds\b|\bdmd\b|dental\s+(?:clinic|center|care)|dentistry|"
    r"oral\s*(?:&|and)?\s*maxillofacial|oral\s+surgery|pediatric\s+dental)",
    re.IGNORECASE,
)

OBVIOUS_NONPROVIDER_CATEGORIES = {
    "acupuncture clinic",
    "addiction treatment center",
    "animal hospital",
    "business administration service",
    "chiropractor",
    "church",
    "government office",
    "health insurance agency",
    "housing society",
    "immigration attorney",
    "insurance agency",
    "make-up artist",
    "market researcher",
    "nail salon",
    "optometrist",
    "orthotics & prosthetics service",
    "registered general nurse",
    "software company",
    "state government office",
    "temp agency",
    "veterinarian",
    "veterinary care",
}


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def triage_maps_profile_review(profile_audit: pd.DataFrame) -> pd.DataFrame:
    """Assign review queues without accepting, excluding, or merging profiles."""

    required = {
        "profile_key",
        "requested_location",
        "title",
        "category",
        "eligibility_review_status",
        "maps_source_status",
        "business_listings_market_covered",
    }
    missing = required - set(profile_audit.columns)
    if missing:
        raise KeyError(f"Maps profile audit is missing columns: {sorted(missing)}")
    frame = profile_audit.copy()
    if frame[["requested_location", "profile_key"]].duplicated().any():
        raise ValueError("Maps profile audit contains duplicate market/profile keys")
    covered = _as_boolean(frame["business_listings_market_covered"])
    maps_only = frame["maps_source_status"].eq("maps_only_exact_profile")
    strong_title = frame["title"].map(
        lambda value: bool(STRONG_DENTAL_PROVIDER_TITLE.search(_text(value)))
    )
    obvious_nonprovider = (
        frame["category"].astype("string").str.strip().str.casefold()
        .isin(OBVIOUS_NONPROVIDER_CATEGORIES)
    )
    status = frame["eligibility_review_status"].astype("string")

    queue = pd.Series("already_seen_in_business_listings", index=frame.index)
    queue.loc[~covered] = "await_business_listings_primary"
    true_maps_only = covered & maps_only
    queue.loc[true_maps_only & status.eq("include_dental_provider")] = (
        "candidate_identity_review"
    )
    queue.loc[
        true_maps_only & status.eq("manual_category_review") & strong_title
    ] = "manual_provider_title_conflict"
    queue.loc[
        true_maps_only
        & status.eq("manual_category_review")
        & ~strong_title
        & obvious_nonprovider
    ] = "manual_likely_nonprovider"
    queue.loc[
        true_maps_only
        & status.eq("manual_category_review")
        & ~strong_title
        & ~obvious_nonprovider
    ] = "manual_institution_review"
    queue.loc[
        true_maps_only
        & status.eq("exclude_non_dentist_category")
        & strong_title
    ] = "excluded_provider_title_conflict"
    queue.loc[
        true_maps_only
        & status.eq("exclude_non_dentist_category")
        & ~strong_title
    ] = "excluded_consistent"

    frame["strong_dental_provider_title"] = strong_title
    frame["obvious_nonprovider_primary_category"] = obvious_nonprovider
    frame["maps_review_queue"] = queue
    frame["automatic_category_decision"] = False
    frame["automatic_profile_or_location_merge"] = False
    return frame


def combine_business_listings_profiles(
    sources: Iterable[tuple[str, pd.DataFrame]],
) -> pd.DataFrame:
    """Combine full Business Listings source rows for identity evidence review."""

    frames: list[pd.DataFrame] = []
    required_detail = {
        "requested_location",
        "title",
        "address",
        "latitude",
        "longitude",
        "phone",
        "domain",
    }
    for source_name, source in sources:
        key_column = "clinic_key" if "clinic_key" in source.columns else "profile_key"
        missing = required_detail - set(source.columns)
        if missing or key_column not in source.columns:
            raise KeyError(
                f"{source_name} is missing columns: {sorted(missing | ({key_column} - set(source.columns)))}"
            )
        if "competition_candidate_included" in source.columns:
            included = _as_boolean(source["competition_candidate_included"])
        elif "provisional_profile_included" in source.columns:
            included = _as_boolean(source["provisional_profile_included"])
        else:
            raise KeyError(f"{source_name} is missing a profile inclusion column")
        frame = source.copy()
        frame["business_profile_key"] = frame[key_column].astype("string").str.strip()
        frame["business_listings_source"] = source_name
        frame["business_listings_profile_included"] = included.to_numpy()
        if "url" not in frame.columns:
            frame["url"] = pd.NA
        frames.append(frame)
    if not frames:
        raise ValueError("At least one Business Listings source is required")
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(
        ["requested_location", "business_profile_key", "business_listings_source"],
        ignore_index=True,
    ).drop_duplicates(
        ["requested_location", "business_profile_key"], keep="first"
    )
    return combined


def build_maps_business_identity_pairs(
    triaged_profiles: pd.DataFrame,
    business_profiles: pd.DataFrame,
) -> pd.DataFrame:
    """Find review-only cross-source identity evidence within the same market."""

    maps_required = {
        "profile_key",
        "requested_location",
        "title",
        "address",
        "latitude",
        "longitude",
        "phone",
        "domain",
        "maps_review_queue",
    }
    missing_maps = maps_required - set(triaged_profiles.columns)
    if missing_maps:
        raise KeyError(f"Triaged Maps profiles are missing: {sorted(missing_maps)}")
    business_required = {
        "business_profile_key",
        "requested_location",
        "title",
        "address",
        "latitude",
        "longitude",
        "phone",
        "domain",
        "url",
        "business_listings_source",
        "business_listings_profile_included",
    }
    missing_business = business_required - set(business_profiles.columns)
    if missing_business:
        raise KeyError(
            f"Business Listings profiles are missing: {sorted(missing_business)}"
        )

    review_maps = triaged_profiles.loc[
        triaged_profiles["maps_review_queue"].isin(
            {
                "candidate_identity_review",
                "manual_provider_title_conflict",
                "manual_institution_review",
                "excluded_provider_title_conflict",
            }
        )
    ].copy()
    records: list[dict[str, Any]] = []
    for _, left in review_maps.iterrows():
        pool = business_profiles.loc[
            business_profiles["requested_location"].eq(left["requested_location"])
        ]
        for _, right in pool.iterrows():
            same_phone = _phone(left["phone"]) is not None and _phone(
                left["phone"]
            ) == _phone(right["phone"])
            same_domain = _domain(left["domain"], left.get("url")) is not None and _domain(
                left["domain"], left.get("url")
            ) == _domain(right["domain"], right["url"])
            left_address = normalize_name(left["address"])
            right_address = normalize_name(right["address"])
            same_address = (
                left_address is not None and left_address == right_address
            )
            distance = _distance_meters(left, right)
            title_similarity = _similarity(left["title"], right["title"])
            close_50m = distance is not None and distance <= 50
            close_500m = distance is not None and distance <= 500
            should_review = (
                same_address
                or (
                    close_50m
                    and (same_phone or same_domain or title_similarity >= 0.55)
                )
                or (same_phone and same_domain)
                or (same_phone and title_similarity >= 0.55)
                or (same_domain and title_similarity >= 0.55)
                or (close_500m and title_similarity >= 0.90)
            )
            if not should_review:
                continue
            records.append(
                {
                    "maps_profile_key": left["profile_key"],
                    "maps_title": left["title"],
                    "maps_address": left["address"],
                    "maps_review_queue": left["maps_review_queue"],
                    "business_profile_key": right["business_profile_key"],
                    "business_title": right["title"],
                    "business_address": right["address"],
                    "business_listings_source": right["business_listings_source"],
                    "business_listings_profile_included": bool(
                        right["business_listings_profile_included"]
                    ),
                    "market": left["requested_location"],
                    "same_phone": same_phone,
                    "same_domain": same_domain,
                    "same_address": same_address,
                    "within_50_meters": close_50m,
                    "distance_meters": (
                        None if distance is None else round(distance, 1)
                    ),
                    "title_similarity": round(title_similarity, 4),
                    "review_priority": (
                        "high"
                        if (same_address or close_50m)
                        and (same_phone or same_domain or title_similarity >= 0.55)
                        else "standard"
                    ),
                    "review_decision": "pending_manual_review",
                }
            )
    columns = [
        "maps_profile_key",
        "maps_title",
        "maps_address",
        "maps_review_queue",
        "business_profile_key",
        "business_title",
        "business_address",
        "business_listings_source",
        "business_listings_profile_included",
        "market",
        "same_phone",
        "same_domain",
        "same_address",
        "within_50_meters",
        "distance_meters",
        "title_similarity",
        "review_priority",
        "review_decision",
    ]
    return pd.DataFrame.from_records(records, columns=columns)


def summarize_maps_only_review(
    triaged_profiles: pd.DataFrame,
    identity_pairs: pd.DataFrame,
) -> dict[str, Any]:
    """Summarize review workload without converting queues into decisions."""

    queue_counts = triaged_profiles["maps_review_queue"].value_counts()
    true_maps_only = triaged_profiles["maps_review_queue"].ne(
        "already_seen_in_business_listings"
    ) & triaged_profiles["maps_review_queue"].ne(
        "await_business_listings_primary"
    )
    paired_keys = set(identity_pairs["maps_profile_key"])
    return {
        "analysis_status": "maps_only_category_and_identity_triage_not_final",
        "api_requests_submitted": 0,
        "true_maps_only_profiles_in_covered_markets": int(true_maps_only.sum()),
        "uncovered_market_profiles": int(
            queue_counts.get("await_business_listings_primary", 0)
        ),
        "review_queue_counts": {
            str(key): int(value) for key, value in queue_counts.items()
        },
        "cross_source_identity_review_pairs": len(identity_pairs),
        "maps_profiles_with_cross_source_identity_candidates": len(paired_keys),
        "automatic_category_decisions": 0,
        "automatic_profile_or_location_merges": 0,
        "interpretation_limit": (
            "Review queues and identity pairs prioritize evidence only. They do not "
            "accept a dental provider, exclude an institution, or merge locations."
        ),
    }
