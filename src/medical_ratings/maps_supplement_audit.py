"""Audit Maps supplement geography and exact overlap with Business Listings."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import Any

import pandas as pd

from medical_ratings.business_listings_comparison import prepare_pilot_candidates


ADDRESS_ZIP_PATTERN = re.compile(
    r",\s*[A-Z]{2}\s+(\d{5})(?:-\d{4})?"
    r"(?:,\s*(?:USA|United States))?\s*$",
    re.IGNORECASE,
)


def recover_missing_maps_zip(candidates: pd.DataFrame) -> pd.DataFrame:
    """Recover a missing source ZIP only from an address-ending state/ZIP pair."""

    required = {"zip", "address"}
    missing = required - set(candidates.columns)
    if missing:
        raise KeyError(f"Maps candidates are missing columns: {sorted(missing)}")
    frame = candidates.copy()
    source_zip = frame["zip"].astype("string").str.strip()
    source_missing = source_zip.isna() | source_zip.eq("")
    extracted = frame["address"].astype("string").str.extract(
        ADDRESS_ZIP_PATTERN, expand=False
    )
    recovered = source_missing & extracted.notna()
    frame["zip_source_value"] = frame["zip"]
    frame.loc[recovered, "zip"] = extracted.loc[recovered]
    frame["zip_resolution_method"] = "source_zip_field"
    frame.loc[recovered, "zip_resolution_method"] = "address_text_fallback"
    frame.loc[source_missing & ~recovered, "zip_resolution_method"] = "unresolved"
    return frame


def audit_maps_candidates(
    candidates: pd.DataFrame,
    regions: Mapping[str, Mapping[str, Any]],
    category_rules: pd.DataFrame,
) -> pd.DataFrame:
    """Apply the established actual-ZIP and primary-category review rules."""

    candidates = recover_missing_maps_zip(candidates)
    frames: list[pd.DataFrame] = []
    for market, group in candidates.groupby("requested_location", sort=True):
        frames.append(
            prepare_pilot_candidates(
                group.copy(),
                regions,
                category_rules,
                target_markets={str(market)},
            )
        )
    if not frames:
        raise ValueError("Maps candidates table is empty")
    reviewed = pd.concat(frames, ignore_index=True)
    reviewed["maps_target_zip_eligible"] = reviewed[
        "market_assignment_status"
    ].eq("eligible_target_zip")
    return reviewed


def build_business_listings_profile_index(
    sources: Iterable[tuple[str, pd.DataFrame]],
) -> pd.DataFrame:
    """Combine included Business Listings profiles without resolving locations."""

    frames: list[pd.DataFrame] = []
    for source_name, source in sources:
        if "requested_location" not in source.columns:
            raise KeyError(f"{source_name} is missing requested_location")
        key_column = "clinic_key" if "clinic_key" in source.columns else "profile_key"
        if key_column not in source.columns:
            raise KeyError(f"{source_name} is missing clinic_key/profile_key")
        if "competition_candidate_included" in source.columns:
            included = _as_boolean(source["competition_candidate_included"])
            inclusion_basis = "adjudicated_competition_candidate"
        elif "provisional_profile_included" in source.columns:
            included = _as_boolean(source["provisional_profile_included"])
            inclusion_basis = "provisional_profile"
        else:
            raise KeyError(
                f"{source_name} is missing an explicit profile inclusion column"
            )
        selected = source.loc[:, ["requested_location", key_column]].copy()
        selected = selected.rename(columns={key_column: "profile_key"})
        selected["business_listings_source"] = source_name
        selected["business_listings_inclusion_basis"] = inclusion_basis
        selected["business_listings_profile_included"] = included.to_numpy()
        frames.append(selected)
    if not frames:
        raise ValueError("At least one Business Listings source is required")
    combined = pd.concat(frames, ignore_index=True)
    combined["requested_location"] = combined["requested_location"].astype("string").str.strip()
    combined["profile_key"] = combined["profile_key"].astype("string").str.strip()
    if combined[["requested_location", "profile_key"]].isna().any().any():
        raise ValueError("Business Listings index contains missing market/profile keys")
    grouped = combined.groupby(
        ["requested_location", "profile_key"], as_index=False, sort=True
    ).agg(
        business_listings_sources=(
            "business_listings_source",
            lambda values: "|".join(sorted(set(values))),
        ),
        business_listings_inclusion_bases=(
            "business_listings_inclusion_basis",
            lambda values: "|".join(sorted(set(values))),
        ),
        business_listings_profile_included=(
            "business_listings_profile_included",
            "max",
        ),
    )
    return grouped


def _as_boolean(values: pd.Series) -> pd.Series:
    """Read boolean columns consistently from in-memory and CSV inputs."""

    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False)
    normalized = values.astype("string").str.strip().str.casefold()
    invalid = set(normalized.dropna()) - {"true", "false", "1", "0"}
    if invalid:
        raise ValueError(f"Invalid boolean values: {sorted(invalid)}")
    return normalized.isin({"true", "1"})


def compare_maps_with_business_listings(
    maps_reviewed: pd.DataFrame,
    business_listings_index: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Create exact profile overlap results for target-ZIP Maps candidates."""

    required_maps = {
        "requested_location",
        "profile_key",
        "maps_target_zip_eligible",
        "eligibility_review_status",
        "primary_legacy_category_group",
    }
    missing_maps = required_maps - set(maps_reviewed.columns)
    if missing_maps:
        raise KeyError(f"Maps review is missing columns: {sorted(missing_maps)}")
    required_business = {
        "requested_location",
        "profile_key",
        "business_listings_sources",
        "business_listings_inclusion_bases",
        "business_listings_profile_included",
    }
    missing_business = required_business - set(business_listings_index.columns)
    if missing_business:
        raise KeyError(
            f"Business Listings index is missing columns: {sorted(missing_business)}"
        )
    eligible = maps_reviewed.loc[maps_reviewed["maps_target_zip_eligible"]].copy()
    compared = eligible.merge(
        business_listings_index,
        on=["requested_location", "profile_key"],
        how="left",
        validate="one_to_one",
    )
    compared["exact_profile_seen_in_business_listings"] = compared[
        "business_listings_sources"
    ].notna()
    compared["exact_profile_included_in_business_listings"] = compared[
        "business_listings_profile_included"
    ].eq(True)
    compared["maps_source_status"] = "maps_only_exact_profile"
    compared.loc[
        compared["exact_profile_seen_in_business_listings"],
        "maps_source_status",
    ] = "seen_but_not_included_in_business_listings"
    compared.loc[
        compared["exact_profile_included_in_business_listings"],
        "maps_source_status",
    ] = "included_in_business_listings"
    business_markets = set(business_listings_index["requested_location"].astype(str))
    compared["business_listings_market_covered"] = compared[
        "requested_location"
    ].isin(business_markets)

    rows: list[dict[str, Any]] = []
    for market, group in compared.groupby("requested_location", sort=True):
        covered = bool(market in business_markets)
        exact_seen = int(group["exact_profile_seen_in_business_listings"].sum())
        exact_included = int(
            group["exact_profile_included_in_business_listings"].sum()
        )
        maps_only = int((~group["exact_profile_seen_in_business_listings"]).sum())
        rows.append(
            {
                "market": market,
                "business_listings_market_covered": covered,
                "target_zip_maps_profiles": len(group),
                "exact_profile_seen_overlap": exact_seen,
                "exact_profile_included_overlap": exact_included,
                "seen_but_not_included_profiles": exact_seen - exact_included,
                "maps_only_exact_profiles": maps_only,
                "maps_only_provisional_dental_profiles": int(
                    (
                        ~group["exact_profile_seen_in_business_listings"]
                        & group["eligibility_review_status"].eq(
                            "include_dental_provider"
                        )
                    ).sum()
                ),
                "maps_only_manual_category_review_profiles": int(
                    (
                        ~group["exact_profile_seen_in_business_listings"]
                        & group["eligibility_review_status"].eq(
                            "manual_category_review"
                        )
                    ).sum()
                ),
            }
        )
    market_summary = pd.DataFrame.from_records(rows)
    covered = compared.loc[compared["business_listings_market_covered"]]
    summary = {
        "analysis_status": "maps_actual_zip_and_exact_source_overlap_not_final",
        "api_requests_submitted": 0,
        "input_maps_profiles": len(maps_reviewed),
        "target_zip_maps_profiles": len(compared),
        "outside_or_unresolved_maps_profiles": len(maps_reviewed) - len(compared),
        "business_listings_covered_markets": sorted(business_markets),
        "business_listings_uncovered_maps_markets": sorted(
            set(compared["requested_location"].astype(str)) - business_markets
        ),
        "covered_market_maps_profiles": len(covered),
        "covered_market_exact_profile_seen_overlap": int(
            covered["exact_profile_seen_in_business_listings"].sum()
        ),
        "covered_market_exact_profile_included_overlap": int(
            covered["exact_profile_included_in_business_listings"].sum()
        ),
        "covered_market_seen_but_not_included_profiles": int(
            (
                covered["exact_profile_seen_in_business_listings"]
                & ~covered["exact_profile_included_in_business_listings"]
            ).sum()
        ),
        "covered_market_maps_only_exact_profiles": int(
            (~covered["exact_profile_seen_in_business_listings"]).sum()
        ),
        "automatic_profile_or_location_merges": 0,
        "interpretation_limit": (
            "Overlap uses exact Google profile identity, not physical-location identity. "
            "Maps-only profiles still require category and location review."
        ),
    }
    return compared, market_summary, summary
