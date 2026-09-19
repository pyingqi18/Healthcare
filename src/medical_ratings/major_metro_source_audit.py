"""Compare major-metro discovery sources on one fused historical reference."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from medical_ratings.business_listings_comparison import (
    COORDINATE_MATCH_MAX_METERS,
    EARTH_RADIUS_METERS,
    PHONE_MATCH_MAX_METERS,
    PILOT_MARKETS,
    REQUIRED_REFERENCE_COLUMNS,
    TITLE_MATCH_MINIMUM,
    _coordinate,
    _phone,
    _title_similarity,
)
from medical_ratings.identifiers import normalize_name


MAJOR_METRO_MARKETS = {"LA_CA_L", "NYC_NY_L"}


def match_reference_locations_indexed(
    reviewed_candidates: pd.DataFrame,
    reference_crosswalk: pd.DataFrame,
    *,
    reference_key_prefix: str | None = "physical_location_final:",
    target_markets: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match old physical locations using fixed identity and coordinate evidence."""

    missing = REQUIRED_REFERENCE_COLUMNS - set(reference_crosswalk.columns)
    if missing:
        raise KeyError(f"Reference crosswalk is missing columns: {sorted(missing)}")
    expected_markets = PILOT_MARKETS if target_markets is None else target_markets
    expected_markets = {str(value).strip() for value in expected_markets}
    if not expected_markets or any(not value for value in expected_markets):
        raise ValueError("Target markets cannot be empty")
    candidate_markets = set(
        reviewed_candidates["requested_location"].dropna().astype(str)
    )
    if candidate_markets != expected_markets:
        raise ValueError(
            "Reviewed candidate markets differ from the requested target markets"
        )
    market_mask = reference_crosswalk["search_location"].isin(expected_markets)
    if reference_key_prefix is None:
        prefix_mask = pd.Series(True, index=reference_crosswalk.index)
    else:
        clean_prefix = str(reference_key_prefix).strip()
        if not clean_prefix:
            raise ValueError("reference_key_prefix cannot be blank")
        prefix_mask = (
            reference_crosswalk["clinic_key"]
            .astype("string")
            .str.startswith(clean_prefix, na=False)
        )
    reference = reference_crosswalk.loc[prefix_mask & market_mask].copy()
    if reference.empty or reference["clinic_key"].duplicated().any():
        raise ValueError("Reference locations must be nonempty and unique")

    eligible_zip = reviewed_candidates.loc[
        reviewed_candidates["market_assignment_status"].eq("eligible_target_zip")
    ].copy()
    eligible_zip["_normalized_address"] = eligible_zip["address"].map(normalize_name)
    eligible_zip["_normalized_phone"] = eligible_zip["phone"].map(_phone)
    eligible_zip["_latitude"] = pd.to_numeric(
        eligible_zip["latitude"], errors="coerce"
    )
    eligible_zip["_longitude"] = pd.to_numeric(
        eligible_zip["longitude"], errors="coerce"
    )
    try:
        from sklearn.neighbors import BallTree
    except ImportError as error:
        raise ImportError("scikit-learn is required for scalable reference matching") from error

    market_indexes: dict[str, dict[str, Any]] = {}
    for market in sorted(expected_markets):
        pool = eligible_zip.loc[eligible_zip["mapped_location"].eq(market)].copy()
        address_index: dict[str, list[Any]] = {}
        for index, value in pool["_normalized_address"].items():
            if value is not None and not pd.isna(value) and str(value):
                address_index.setdefault(str(value), []).append(index)
        valid = pool["_latitude"].between(-90, 90) & pool["_longitude"].between(-180, 180)
        coordinate_indexes = pool.index[valid].to_numpy()
        tree = None
        if len(coordinate_indexes):
            coordinates = np.radians(
                pool.loc[coordinate_indexes, ["_latitude", "_longitude"]].to_numpy()
            )
            tree = BallTree(coordinates, metric="haversine")
        market_indexes[market] = {
            "pool": pool,
            "address_index": address_index,
            "coordinate_indexes": coordinate_indexes,
            "tree": tree,
        }

    pair_records: list[dict[str, Any]] = []
    reference_records: list[dict[str, Any]] = []
    for ref in reference.itertuples(index=False):
        indexed = market_indexes[str(ref.search_location)]
        pool = indexed["pool"]
        tree = indexed["tree"]
        coordinate_indexes = indexed["coordinate_indexes"]
        ref_latitude = _coordinate(ref.latitude, -90, 90)
        ref_longitude = _coordinate(ref.longitude, -180, 180)
        reference_address = normalize_name(ref.address)
        reference_phone = _phone(ref.phone)
        address_matches = set(
            indexed["address_index"].get(str(reference_address), [])
            if reference_address is not None
            else []
        )
        nearby_distances: dict[Any, float] = {}
        nearest_index: Any | None = None
        if tree is not None and ref_latitude is not None and ref_longitude is not None:
            point = np.radians([[ref_latitude, ref_longitude]])
            positions, angular_distances = tree.query_radius(
                point,
                r=PHONE_MATCH_MAX_METERS / EARTH_RADIUS_METERS,
                return_distance=True,
                sort_results=True,
            )
            for position, angular_distance in zip(positions[0], angular_distances[0]):
                nearby_distances[coordinate_indexes[int(position)]] = (
                    float(angular_distance) * EARTH_RADIUS_METERS
                )
            _, nearest_positions = tree.query(point, k=1)
            nearest_index = coordinate_indexes[int(nearest_positions[0][0])]
        elif not pool.empty:
            nearest_index = pool.index[0]

        evaluation_indexes = address_matches | set(nearby_distances)

        def distance_for(candidate_index: Any) -> float | None:
            if candidate_index in nearby_distances:
                return nearby_distances[candidate_index]
            candidate = pool.loc[candidate_index]
            candidate_latitude = _coordinate(candidate["_latitude"], -90, 90)
            candidate_longitude = _coordinate(candidate["_longitude"], -180, 180)
            if None in {
                ref_latitude,
                ref_longitude,
                candidate_latitude,
                candidate_longitude,
            }:
                return None
            lat_1, lon_1, lat_2, lon_2 = map(
                math.radians,
                (
                    ref_latitude,
                    ref_longitude,
                    candidate_latitude,
                    candidate_longitude,
                ),
            )
            delta_latitude = lat_2 - lat_1
            delta_longitude = lon_2 - lon_1
            value = (
                math.sin(delta_latitude / 2) ** 2
                + math.cos(lat_1)
                * math.cos(lat_2)
                * math.sin(delta_longitude / 2) ** 2
            )
            return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(min(1.0, value)))

        def build_record(candidate_index: Any) -> dict[str, Any]:
            candidate = pool.loc[candidate_index]
            distance = distance_for(candidate_index)
            candidate_same_address = candidate_index in address_matches
            candidate_same_phone = bool(
                reference_phone
                and candidate["_normalized_phone"] == reference_phone
            )
            title_similarity = _title_similarity(ref.title, candidate["title"])
            within_10 = distance is not None and distance <= COORDINATE_MATCH_MAX_METERS
            within_100 = distance is not None and distance <= PHONE_MATCH_MAX_METERS
            coordinate_title_match = within_10 and title_similarity >= TITLE_MATCH_MINIMUM
            phone_near_match = candidate_same_phone and within_100
            fixed_rule_match = (
                candidate_same_address or coordinate_title_match or phone_near_match
            )
            coordinate_review = within_10 and not fixed_rule_match
            if candidate_same_address:
                matching_evidence = "same_normalized_address"
            elif phone_near_match:
                matching_evidence = "same_phone_within_100m"
            elif coordinate_title_match:
                matching_evidence = "within_10m_and_title_similarity_at_least_0p8"
            elif coordinate_review:
                matching_evidence = "coordinate_only_within_10m_review"
            else:
                matching_evidence = "nearest_candidate_only"
            return {
                "reference_key": ref.clinic_key,
                "market": ref.search_location,
                "reference_title": ref.title,
                "reference_address": ref.address,
                "candidate_key": candidate["clinic_key"],
                "candidate_cid": candidate["cid"],
                "candidate_title": candidate["title"],
                "candidate_category": candidate["category"],
                "candidate_address": candidate["address"],
                "eligibility_review_status": candidate["eligibility_review_status"],
                "same_normalized_address": candidate_same_address,
                "same_phone": candidate_same_phone,
                "distance_meters": None if distance is None else round(distance, 3),
                "within_10_meters": within_10,
                "title_similarity": round(float(title_similarity), 4),
                "matching_evidence": matching_evidence,
                "fixed_rule_match": fixed_rule_match,
            }

        evaluated = [
            build_record(index)
            for index in sorted(evaluation_indexes, key=lambda value: str(value))
        ]
        review_records = [
            row
            for row in evaluated
            if row["fixed_rule_match"] or row["matching_evidence"] == "coordinate_only_within_10m_review"
        ]
        candidates_for_reference = [row for row in evaluated if row["fixed_rule_match"]]
        pair_records.extend(review_records)
        nearest_record: dict[str, Any] | None = None
        if nearest_index is not None:
            nearest_record = build_record(nearest_index)

        include_matches = [
            row
            for row in candidates_for_reference
            if row["eligibility_review_status"] == "include_dental_provider"
        ]
        ranked = sorted(
            candidates_for_reference,
            key=lambda row: (
                row["eligibility_review_status"] != "include_dental_provider",
                not row["same_normalized_address"],
                not row["same_phone"],
                row["distance_meters"] if row["distance_meters"] is not None else math.inf,
                -row["title_similarity"],
                str(row["candidate_key"]),
            ),
        )
        best = ranked[0] if ranked else nearest_record
        reference_records.append(
            {
                "reference_key": ref.clinic_key,
                "market": ref.search_location,
                "reference_title": ref.title,
                "reference_address": ref.address,
                "discovered": bool(candidates_for_reference),
                "discovered_with_provisional_include": bool(include_matches),
                "matched_candidate_count": len(candidates_for_reference),
                "matched_included_candidate_count": len(include_matches),
                "coordinate_only_review_candidate_count": sum(
                    row["matching_evidence"] == "coordinate_only_within_10m_review"
                    for row in review_records
                ),
                "best_candidate_key": None if best is None else best["candidate_key"],
                "best_candidate_cid": None if best is None else best["candidate_cid"],
                "best_candidate_title": None if best is None else best["candidate_title"],
                "best_candidate_category": None if best is None else best["candidate_category"],
                "best_candidate_status": None if best is None else best["eligibility_review_status"],
                "best_candidate_address": None if best is None else best["candidate_address"],
                "best_distance_meters": None if best is None else best["distance_meters"],
                "best_same_address": False if best is None else best["same_normalized_address"],
                "best_same_phone": False if best is None else best["same_phone"],
                "best_title_similarity": None if best is None else best["title_similarity"],
                "best_matching_evidence": (
                    None if best is None else best["matching_evidence"]
                ),
                "automatic_coordinate_only_match_performed": False,
            }
        )
    matches = pd.DataFrame.from_records(reference_records).sort_values(
        ["market", "reference_key"], ignore_index=True
    )
    pairs = pd.DataFrame.from_records(pair_records)
    return matches, pairs

def compare_major_metro_exact_profiles(
    business_reviewed: pd.DataFrame,
    maps_reviewed: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare target-ZIP Maps and Business Listings by exact Google identity."""

    required = {"requested_location", "profile_key", "eligibility_review_status"}
    for label, frame in [
        ("Business Listings", business_reviewed),
        ("Maps Standard", maps_reviewed),
    ]:
        missing = required - set(frame.columns)
        if missing:
            raise KeyError(f"{label} candidates are missing columns: {sorted(missing)}")
        markets = set(frame["requested_location"].dropna().astype(str))
        if markets != MAJOR_METRO_MARKETS:
            raise ValueError(f"{label} candidates must contain exactly LA and NYC")
        if frame.duplicated(["requested_location", "profile_key"]).any():
            raise ValueError(f"{label} requires unique market-profile keys")

    business = business_reviewed.loc[
        business_reviewed["market_assignment_status"].eq("eligible_target_zip"),
        ["requested_location", "profile_key", "eligibility_review_status"],
    ].copy()
    business["business_listings_profile_seen"] = True
    business["business_listings_profile_included"] = business[
        "eligibility_review_status"
    ].eq("include_dental_provider")
    business = business.rename(
        columns={
            "eligibility_review_status": "business_listings_eligibility_status"
        }
    )
    maps = maps_reviewed.loc[
        maps_reviewed["market_assignment_status"].eq("eligible_target_zip")
    ].copy()
    stale_columns = [
        "business_listings_sources",
        "business_listings_inclusion_bases",
        "business_listings_profile_included",
        "exact_profile_seen_in_business_listings",
        "exact_profile_included_in_business_listings",
        "maps_source_status",
        "business_listings_market_covered",
    ]
    maps = maps.drop(columns=[column for column in stale_columns if column in maps])
    compared = maps.merge(
        business,
        on=["requested_location", "profile_key"],
        how="left",
        validate="one_to_one",
    )
    seen = compared["business_listings_profile_seen"].eq(True)
    included = compared["business_listings_profile_included"].eq(True)
    compared["business_listings_profile_seen"] = seen.astype(bool)
    compared["business_listings_profile_included"] = included.astype(bool)
    compared["maps_business_exact_profile_status"] = "maps_only_exact_profile"
    compared.loc[seen, "maps_business_exact_profile_status"] = (
        "seen_but_not_included_in_business_listings"
    )
    compared.loc[included, "maps_business_exact_profile_status"] = (
        "included_in_business_listings"
    )

    records: list[dict[str, Any]] = []
    for market, group in compared.groupby("requested_location", sort=True):
        records.append(
            {
                "market": str(market),
                "maps_standard_target_zip_profiles": len(group),
                "maps_exact_profile_seen_in_business_listings": int(
                    group["business_listings_profile_seen"].sum()
                ),
                "maps_exact_profile_included_in_business_listings": int(
                    group["business_listings_profile_included"].sum()
                ),
                "maps_seen_but_not_included_profiles": int(
                    group["maps_business_exact_profile_status"]
                    .eq("seen_but_not_included_in_business_listings")
                    .sum()
                ),
                "maps_only_exact_profiles": int(
                    group["maps_business_exact_profile_status"]
                    .eq("maps_only_exact_profile")
                    .sum()
                ),
            }
        )
    return compared.reset_index(drop=True), pd.DataFrame.from_records(records)


def build_major_metro_three_way_summary(
    business_reviewed: pd.DataFrame,
    maps_reviewed: pd.DataFrame,
    exact_overlap_by_market: pd.DataFrame,
    fused_reference_universe: pd.DataFrame,
    business_reference_matches: pd.DataFrame,
    maps_reference_matches: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Report three comparisons without treating profiles as locations."""

    records: list[dict[str, Any]] = []
    exact_index = exact_overlap_by_market.set_index("market")
    for market in sorted(MAJOR_METRO_MARKETS):
        business = business_reviewed.loc[
            business_reviewed["requested_location"].eq(market)
        ]
        maps = maps_reviewed.loc[maps_reviewed["requested_location"].eq(market)]
        universe = fused_reference_universe.loc[
            fused_reference_universe["search_location"].eq(market)
        ]
        business_matches = business_reference_matches.loc[
            business_reference_matches["market"].eq(market)
        ]
        maps_matches = maps_reference_matches.loc[
            maps_reference_matches["market"].eq(market)
        ]
        exact = exact_index.loc[market]
        eligible = int(
            universe["reference_geography_status"].eq("eligible_target_zip").sum()
        )
        business_discovered = int(business_matches["discovered"].sum())
        maps_discovered = int(maps_matches["discovered"].sum())
        records.append(
            {
                "market": market,
                "business_listings_unique_profiles": len(business),
                "business_listings_target_zip_profiles": int(
                    business["market_assignment_status"].eq("eligible_target_zip").sum()
                ),
                "maps_standard_unique_profiles": len(maps),
                "maps_standard_target_zip_profiles": int(
                    maps["market_assignment_status"].eq("eligible_target_zip").sum()
                ),
                "fused_historical_units_labeled_as_market": len(universe),
                "fused_historical_target_zip_units": eligible,
                "fused_historical_outside_target_zip_units": int(
                    universe["reference_geography_status"].eq("outside_target_zip").sum()
                ),
                "fused_historical_missing_zip_units": int(
                    universe["reference_geography_status"].eq("missing_zip").sum()
                ),
                "business_listings_discovered_fused_units": business_discovered,
                "business_listings_fused_reference_recall": (
                    business_discovered / eligible if eligible else None
                ),
                "maps_standard_discovered_fused_units": maps_discovered,
                "maps_standard_fused_reference_recall": (
                    maps_discovered / eligible if eligible else None
                ),
                "maps_exact_profile_seen_in_business_listings": int(
                    exact["maps_exact_profile_seen_in_business_listings"]
                ),
                "maps_business_exact_profile_overlap": (
                    int(exact["maps_exact_profile_seen_in_business_listings"])
                    / int(exact["maps_standard_target_zip_profiles"])
                ),
                "maps_only_exact_profiles": int(exact["maps_only_exact_profiles"]),
            }
        )
    by_market = pd.DataFrame.from_records(records)
    reference_total = int(by_market["fused_historical_target_zip_units"].sum())
    business_total = int(
        by_market["business_listings_discovered_fused_units"].sum()
    )
    maps_total = int(by_market["maps_standard_discovered_fused_units"].sum())
    maps_profiles = int(by_market["maps_standard_target_zip_profiles"].sum())
    exact_total = int(
        by_market["maps_exact_profile_seen_in_business_listings"].sum()
    )
    summary = {
        "analysis_status": "major_metro_three_way_source_audit_not_final",
        "api_requests_submitted": 0,
        "markets_audited": sorted(MAJOR_METRO_MARKETS),
        "historical_reference_name": "corrected_v1_fused_historical_reference",
        "historical_reference_composition": "legacy_plus_external_already_fused",
        "historical_component_origin_separable_in_crosswalk": False,
        "fused_historical_target_zip_units": reference_total,
        "business_listings_discovered_fused_units": business_total,
        "business_listings_fused_reference_recall": business_total / reference_total,
        "maps_standard_discovered_fused_units": maps_total,
        "maps_standard_fused_reference_recall": maps_total / reference_total,
        "maps_standard_target_zip_profiles": maps_profiles,
        "maps_exact_profile_seen_in_business_listings": exact_total,
        "maps_business_exact_profile_overlap": exact_total / maps_profiles,
        "maps_only_exact_profiles": int(by_market["maps_only_exact_profiles"].sum()),
        "matching_rule": "frozen_address_phone_distance_and_title_identity_rules",
        "matching_engine": "indexed_haversine_candidate_search",
        "regression_balltree_modified": False,
        "automatic_profile_or_location_merges": 0,
        "interpretation_limits": [
            "The fused historical reference already contains legacy and external records; the supplied crosswalk cannot split their original sources.",
            "Maps Standard used two core keyword tasks per market and is not a complete census of major-metro profiles.",
            "Exact Maps-Business overlap identifies the same Google profile, not the same physical location.",
            "Reference recall uses target-ZIP competition units and the same frozen identity rules for both discovery sources.",
        ],
    }
    return by_market, summary
