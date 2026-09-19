"""Prioritize Business Listings location blocks for manual review."""

from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from medical_ratings.identifiers import normalize_name


EARTH_RADIUS_METERS = 6_371_008.8
REQUIRED_BLOCK_COLUMNS = {
    "clinic_key",
    "physical_location_group",
    "location_group_size",
    "mapped_location",
    "title",
    "address",
    "phone",
    "domain",
    "latitude",
    "longitude",
    "profile_role",
    "suggested_canonical_profile",
}
REQUIRED_PAIR_COLUMNS = {
    "left_clinic_key",
    "right_clinic_key",
    "same_phone",
    "same_domain",
    "same_address",
    "within_50_meters",
    "title_similarity",
}
UNIT_PATTERN = re.compile(
    r"(?:\s+|,)(?:suite|ste|unit|floor|fl|room|rm|#)\s*[a-z0-9-]+(?:\s|,|$)",
    re.I,
)


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


def _text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _phone(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def _domain(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.hostname or "").casefold().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _base_address(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    stripped = UNIT_PATTERN.sub(" ", f" {text} ")
    return normalize_name(stripped)


def _coordinate(value: Any, lower: float, upper: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or not lower <= number <= upper:
        return None
    return number


def _distance(left: pd.Series, right: pd.Series) -> float | None:
    lat_1 = _coordinate(left["latitude"], -90, 90)
    lon_1 = _coordinate(left["longitude"], -180, 180)
    lat_2 = _coordinate(right["latitude"], -90, 90)
    lon_2 = _coordinate(right["longitude"], -180, 180)
    if None in {lat_1, lon_1, lat_2, lon_2}:
        return None
    lat_1, lon_1, lat_2, lon_2 = map(math.radians, (lat_1, lon_1, lat_2, lon_2))
    delta_latitude = lat_2 - lat_1
    delta_longitude = lon_2 - lon_1
    haversine = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(lat_1) * math.cos(lat_2) * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(min(1.0, haversine)))


def _strong_edge(row: pd.Series) -> bool:
    same_phone = _boolean(row["same_phone"])
    same_domain = _boolean(row["same_domain"])
    same_address = _boolean(row["same_address"])
    within_50 = _boolean(row["within_50_meters"])
    similarity = float(row["title_similarity"])
    return (
        (same_address and (same_phone or same_domain))
        or (within_50 and (same_phone or same_domain))
        or (within_50 and similarity >= 0.90)
    )


def _triage_tier(
    *,
    profile_count: int,
    base_address_count: int,
    phone_count: int,
    phone_coverage: int,
    domain_count: int,
    domain_coverage: int,
    organization_count: int,
    maximum_distance_meters: float | None,
    edge_density: float,
) -> tuple[str, str]:
    multiple_base_addresses = base_address_count > 1
    wide_spread = maximum_distance_meters is None or maximum_distance_meters > 100
    sparse_graph = edge_density < 0.50
    if multiple_base_addresses or wide_spread or sparse_graph or organization_count > 1:
        reasons: list[str] = []
        if multiple_base_addresses:
            reasons.append("multiple base addresses")
        if wide_spread:
            reasons.append("coordinate spread exceeds 100m or is unavailable")
        if sparse_graph:
            reasons.append("strong-edge density below 0.50")
        if organization_count > 1:
            reasons.append("multiple organization profiles")
        return "complex_review", "; ".join(reasons)

    shared_phone = phone_count == 1 and phone_coverage == profile_count
    shared_domain = domain_count == 1 and domain_coverage == profile_count
    if (
        base_address_count == 1
        and maximum_distance_meters is not None
        and maximum_distance_meters <= 50
        and edge_density >= 0.80
        and (shared_phone or shared_domain)
    ):
        signal = "shared phone" if shared_phone else "shared domain"
        return "routine_shared_identity", f"one base address; {signal}; dense strong-edge graph"
    return "focused_review", "same general location but identity evidence is incomplete or mixed"


def triage_location_blocks(
    blocks: pd.DataFrame,
    pairs: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return one review row per multi-profile block and profiles sorted by tier."""

    missing_blocks = REQUIRED_BLOCK_COLUMNS - set(blocks.columns)
    if missing_blocks:
        raise KeyError(f"Location blocks are missing columns: {sorted(missing_blocks)}")
    missing_pairs = REQUIRED_PAIR_COLUMNS - set(pairs.columns)
    if missing_pairs:
        raise KeyError(f"Location pairs are missing columns: {sorted(missing_pairs)}")
    if blocks["clinic_key"].isna().any() or blocks["clinic_key"].duplicated().any():
        raise ValueError("Location blocks require unique nonblank clinic_key values")

    multi = blocks.loc[blocks["location_group_size"].gt(1)].copy()
    records: list[dict[str, Any]] = []
    for group_id, group in multi.groupby("physical_location_group", sort=True):
        keys = set(group["clinic_key"].astype(str))
        group_pairs = pairs.loc[
            pairs["left_clinic_key"].astype(str).isin(keys)
            & pairs["right_clinic_key"].astype(str).isin(keys)
        ].copy()
        strong_edges = int(group_pairs.apply(_strong_edge, axis=1).sum())
        possible_edges = len(group) * (len(group) - 1) // 2
        edge_density = strong_edges / possible_edges

        distances: list[float] = []
        indexed = group.reset_index(drop=True)
        for left in range(len(indexed)):
            for right in range(left + 1, len(indexed)):
                distance = _distance(indexed.iloc[left], indexed.iloc[right])
                if distance is not None:
                    distances.append(distance)
        maximum_distance = max(distances) if distances else None
        base_addresses = {
            value for value in group["address"].map(_base_address) if value is not None
        }
        phones = [value for value in group["phone"].map(_phone) if value is not None]
        domains = [value for value in group["domain"].map(_domain) if value is not None]
        role_counts = group["profile_role"].value_counts()
        organization_count = int(role_counts.get("organization", 0))
        tier, reason = _triage_tier(
            profile_count=len(group),
            base_address_count=len(base_addresses),
            phone_count=len(set(phones)),
            phone_coverage=len(phones),
            domain_count=len(set(domains)),
            domain_coverage=len(domains),
            organization_count=organization_count,
            maximum_distance_meters=maximum_distance,
            edge_density=edge_density,
        )
        canonical = group.loc[group["suggested_canonical_profile"].map(_boolean)]
        records.append(
            {
                "physical_location_group": group_id,
                "mapped_location": str(group["mapped_location"].iloc[0]),
                "profile_count": len(group),
                "base_address_count": len(base_addresses),
                "exact_address_count": int(group["address"].nunique(dropna=True)),
                "unique_phone_count": len(set(phones)),
                "phone_coverage_profiles": len(phones),
                "unique_domain_count": len(set(domains)),
                "domain_coverage_profiles": len(domains),
                "organization_profiles": organization_count,
                "individual_provider_profiles": int(
                    role_counts.get("individual_provider", 0)
                ),
                "uncertain_profiles": int(role_counts.get("uncertain", 0)),
                "strong_edge_count": strong_edges,
                "possible_edge_count": possible_edges,
                "strong_edge_density": round(edge_density, 4),
                "maximum_coordinate_spread_meters": (
                    None if maximum_distance is None else round(maximum_distance, 1)
                ),
                "suggested_canonical_key": (
                    None if canonical.empty else canonical.iloc[0]["clinic_key"]
                ),
                "suggested_canonical_title": (
                    None if canonical.empty else canonical.iloc[0]["title"]
                ),
                "review_tier": tier,
                "review_reason": reason,
                "manual_decision": "pending_manual_review",
            }
        )

    block_summary = pd.DataFrame.from_records(records)
    tier_order = {
        "complex_review": 0,
        "focused_review": 1,
        "routine_shared_identity": 2,
    }
    block_summary["_tier_order"] = block_summary["review_tier"].map(tier_order)
    block_summary = block_summary.sort_values(
        ["_tier_order", "profile_count", "mapped_location", "physical_location_group"],
        ascending=[True, False, True, True],
    ).drop(columns="_tier_order").reset_index(drop=True)

    profiles = multi.merge(
        block_summary[[
            "physical_location_group",
            "review_tier",
            "review_reason",
            "strong_edge_density",
            "maximum_coordinate_spread_meters",
        ]],
        on="physical_location_group",
        how="left",
        validate="many_to_one",
    )
    profiles["_tier_order"] = profiles["review_tier"].map(tier_order)
    profiles = profiles.sort_values(
        ["_tier_order", "location_group_size", "physical_location_group", "suggested_canonical_profile", "title"],
        ascending=[True, False, True, False, True],
    ).drop(columns="_tier_order").reset_index(drop=True)

    tier_counts = block_summary["review_tier"].value_counts()
    profile_tier_counts = profiles["review_tier"].value_counts()
    summary = {
        "analysis_status": "location_block_triage_not_final",
        "api_requests_submitted": 0,
        "multi_profile_review_blocks": len(block_summary),
        "profiles_in_multi_profile_blocks": len(profiles),
        "blocks_by_review_tier": {
            tier: int(tier_counts.get(tier, 0))
            for tier in tier_order
        },
        "profiles_by_review_tier": {
            tier: int(profile_tier_counts.get(tier, 0))
            for tier in tier_order
        },
        "automatic_profile_or_location_merges": 0,
        "interpretation_limit": (
            "Tiers prioritize manual review only. A routine block is not an approved merge."
        ),
    }
    return block_summary, profiles, summary

