"""Build review-only profile-to-location evidence for Business Listings."""

from __future__ import annotations

from typing import Any

import pandas as pd

from medical_ratings.duplicate_candidate_audit import (
    build_duplicate_candidate_pairs,
)
from medical_ratings.physical_location_groups import (
    build_physical_location_review,
)


REQUIRED_COLUMNS = {
    "clinic_key",
    "cid",
    "title",
    "address",
    "latitude",
    "longitude",
    "phone",
    "domain",
    "mapped_location",
    "votes_count",
    "observation_count",
    "competition_candidate_included",
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


def prepare_location_audit_candidates(
    adjudicated_candidates: pd.DataFrame,
) -> pd.DataFrame:
    """Adapt adjudicated pilot profiles to the existing review-only audit schema."""

    missing = REQUIRED_COLUMNS - set(adjudicated_candidates.columns)
    if missing:
        raise KeyError(f"Adjudicated candidates are missing columns: {sorted(missing)}")
    if adjudicated_candidates.empty:
        raise ValueError("Adjudicated candidates table is empty")
    if (
        adjudicated_candidates["clinic_key"].isna().any()
        or adjudicated_candidates["clinic_key"].duplicated().any()
    ):
        raise ValueError("Adjudicated candidates require unique nonblank clinic_key values")

    frame = adjudicated_candidates.copy()
    frame["final_included"] = frame["competition_candidate_included"].map(_boolean)
    if "url" not in frame.columns:
        frame["url"] = pd.NA
    included = frame["final_included"]
    if frame.loc[included, "mapped_location"].isna().any():
        raise ValueError("Included competition candidates require mapped_location")
    return frame


def build_business_listings_location_audit(
    adjudicated_candidates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return candidate pairs, provisional review blocks, and an audit summary."""

    candidates = prepare_location_audit_candidates(adjudicated_candidates)
    pairs = build_duplicate_candidate_pairs(candidates)
    review = build_physical_location_review(candidates, pairs)
    flagged_keys = set(pairs["left_clinic_key"]) | set(pairs["right_clinic_key"])
    grouped = review.loc[review["location_group_size"].gt(1)]
    largest = int(review["location_group_size"].max()) if len(review) else 0
    summary = {
        "analysis_status": "profile_to_location_review_blocks_not_final",
        "api_requests_submitted": 0,
        "competition_candidate_profiles": len(review),
        "review_pairs": len(pairs),
        "profiles_in_review_pairs": len(flagged_keys),
        "pairs_by_priority": {
            str(key): int(value)
            for key, value in pairs["review_priority"]
            .value_counts()
            .sort_index()
            .items()
        },
        "evidence_pair_counts": {
            column: int(pairs[column].sum())
            for column in (
                "same_phone",
                "same_domain",
                "same_address",
                "within_50_meters",
            )
        },
        "provisional_review_blocks": int(
            review["physical_location_group"].nunique()
        ),
        "singleton_review_blocks": int(
            review.loc[
                review["location_group_size"].eq(1), "physical_location_group"
            ].nunique()
        ),
        "multi_profile_review_blocks": int(
            grouped["physical_location_group"].nunique()
        ),
        "profiles_in_multi_profile_blocks": len(grouped),
        "largest_review_block_profiles": largest,
        "suggested_noncanonical_profiles": int(
            (~review["suggested_canonical_profile"]).sum()
        ),
        "automatic_profile_or_location_merges": 0,
        "interpretation_limit": (
            "Connected components are manual-review blocks, not confirmed physical "
            "locations. Shared addresses can contain multiple independent practices, "
            "and transitive evidence can create chains."
        ),
        "next_required_action": (
            "Review all multi-profile blocks before assigning final location IDs."
        ),
    }
    return pairs, review, summary
