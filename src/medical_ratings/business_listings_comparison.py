"""Audit Business Listings pilot eligibility and legacy-reference recall."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Any

import numpy as np
import pandas as pd

from medical_ratings.candidate_audit import _zip_market_lookup
from medical_ratings.candidate_eligibility import apply_candidate_eligibility_review
from medical_ratings.business_listings_pilot import evaluate_pilot_recall
from medical_ratings.identifiers import normalize_name, normalize_zip


EARTH_RADIUS_METERS = 6_371_008.8
COORDINATE_MATCH_MAX_METERS = 10.0
PHONE_MATCH_MAX_METERS = 100.0
TITLE_MATCH_MINIMUM = 0.8
CANADIAN_POSTAL_PATTERN = re.compile(
    r"^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTVWXYZ][ -]?\d[ABCEGHJ-NPRSTVWXYZ]\d$",
    re.IGNORECASE,
)
PILOT_MARKETS = {"Malone_NY_S", "Syracuse_NY_M"}
REQUIRED_CANDIDATE_COLUMNS = {
    "profile_key",
    "cid",
    "place_id",
    "requested_location",
    "title",
    "category",
    "address",
    "zip",
    "latitude",
    "longitude",
    "phone",
    "domain",
}
REQUIRED_REFERENCE_COLUMNS = {
    "clinic_key",
    "search_location",
    "title",
    "address",
    "zip",
    "latitude",
    "longitude",
    "phone",
    "domain",
}


def build_competition_unit_references(
    reference_crosswalk: pd.DataFrame,
    *,
    target_markets: set[str],
) -> pd.DataFrame:
    """Collapse legacy profiles to one canonical row per competition unit."""

    required = REQUIRED_REFERENCE_COLUMNS | {"competition_unit_id"}
    missing = required - set(reference_crosswalk.columns)
    if missing:
        raise KeyError(f"Reference crosswalk is missing columns: {sorted(missing)}")
    markets = {str(value).strip() for value in target_markets}
    if not markets or any(not value for value in markets):
        raise ValueError("Target markets cannot be empty")
    selected = reference_crosswalk.loc[
        reference_crosswalk["search_location"].isin(markets)
    ].copy()
    if selected.empty:
        raise ValueError("No legacy competition units were found for target markets")
    unit_ids = selected["competition_unit_id"].astype("string").str.strip()
    if unit_ids.isna().any() or unit_ids.eq("").any():
        raise ValueError("Reference crosswalk contains missing competition_unit_id")
    selected["competition_unit_id"] = unit_ids

    records: list[dict[str, Any]] = []
    identity_columns = [
        "title",
        "address",
        "zip",
        "latitude",
        "longitude",
        "phone",
        "domain",
    ]
    for unit_id, group in selected.groupby("competition_unit_id", sort=True):
        unit_markets = set(group["search_location"].dropna().astype(str))
        if len(unit_markets) != 1:
            raise ValueError("One competition unit appears in multiple markets")
        completeness = group[identity_columns].notna().sum(axis=1)
        canonical_index = completeness.sort_values(
            ascending=False, kind="stable"
        ).index[0]
        canonical = group.loc[canonical_index]
        source_keys = sorted(set(group["clinic_key"].dropna().astype(str)))
        source_prefixes = sorted(
            {
                value.split(":", 1)[0] if ":" in value else "unprefixed"
                for value in source_keys
            }
        )
        records.append(
            {
                "clinic_key": str(unit_id),
                "search_location": str(canonical["search_location"]),
                "title": canonical["title"],
                "address": canonical["address"],
                "zip": canonical["zip"],
                "latitude": canonical["latitude"],
                "longitude": canonical["longitude"],
                "phone": canonical["phone"],
                "domain": canonical["domain"],
                "reference_source_profile_count": len(group),
                "reference_source_clinic_keys": "|".join(source_keys),
                "reference_source_key_prefixes": "|".join(source_prefixes),
            }
        )
    references = pd.DataFrame.from_records(records)
    if references["clinic_key"].duplicated().any():
        raise ValueError("Competition-unit reference keys must be unique")
    return references.sort_values(
        ["search_location", "clinic_key"], ignore_index=True
    )


def classify_competition_unit_reference_geography(
    references: pd.DataFrame,
    regions: Mapping[str, Mapping[str, Any]],
    *,
    target_markets: set[str],
) -> pd.DataFrame:
    """Classify legacy competition units by their actual ZIP geography."""

    required = {"clinic_key", "search_location", "zip"}
    missing = required - set(references.columns)
    if missing:
        raise KeyError(f"Competition-unit references are missing columns: {sorted(missing)}")
    markets = {str(value).strip() for value in target_markets}
    if not markets or any(not value for value in markets):
        raise ValueError("Target markets cannot be empty")
    result = references.copy()
    source_zip_missing = result["zip"].isna() | result["zip"].astype("string").str.strip().eq("")
    result["normalized_zip"] = result["zip"].map(normalize_zip)
    zip_market = _zip_market_lookup(regions, markets)
    result["actual_zip_market"] = result["normalized_zip"].map(zip_market)
    result["reference_geography_status"] = np.select(
        [
            source_zip_missing | result["normalized_zip"].eq(""),
            result["actual_zip_market"].isin(markets),
        ],
        ["missing_zip", "eligible_target_zip"],
        default="outside_target_zip",
    )
    return result


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _phone(value: Any) -> str:
    digits = re.sub(r"\D", "", _text(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


def _coordinate(value: Any, lower: float, upper: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or not lower <= number <= upper:
        return None
    return number


def _distance_meters(left: pd.Series, right: pd.Series) -> float | None:
    lat_1 = _coordinate(left["latitude"], -90, 90)
    lon_1 = _coordinate(left["longitude"], -180, 180)
    lat_2 = _coordinate(right["latitude"], -90, 90)
    lon_2 = _coordinate(right["longitude"], -180, 180)
    if None in {lat_1, lon_1, lat_2, lon_2}:
        return None
    lat_1_r, lon_1_r, lat_2_r, lon_2_r = map(
        math.radians, (lat_1, lon_1, lat_2, lon_2)
    )
    delta_latitude = lat_2_r - lat_1_r
    delta_longitude = lon_2_r - lon_1_r
    value = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(lat_1_r)
        * math.cos(lat_2_r)
        * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(min(1.0, value)))


def _title_similarity(left: Any, right: Any) -> float:
    left_name = normalize_name(left)
    right_name = normalize_name(right)
    if left_name is None or right_name is None:
        return 0.0
    return SequenceMatcher(None, left_name, right_name).ratio()


def _postal_code_status(raw_value: Any, normalized_zip: Any) -> str:
    """Distinguish missing, US, Canadian, and unrecognized postal evidence."""

    raw = _text(raw_value)
    if not raw:
        return "missing"
    if _text(normalized_zip):
        return "us_zip"
    if CANADIAN_POSTAL_PATTERN.fullmatch(raw):
        return "non_us_postal"
    return "unrecognized_postal"


def prepare_pilot_candidates(
    candidates: pd.DataFrame,
    regions: Mapping[str, Mapping[str, Any]],
    category_rules: pd.DataFrame,
    *,
    target_markets: set[str] | None = None,
) -> pd.DataFrame:
    """Assign actual-ZIP and primary-category statuses without dropping rows."""

    missing = REQUIRED_CANDIDATE_COLUMNS - set(candidates.columns)
    if missing:
        raise KeyError(f"Pilot candidates are missing columns: {sorted(missing)}")
    if candidates.empty:
        raise ValueError("Pilot candidates table is empty")
    if candidates["profile_key"].isna().any() or candidates["profile_key"].duplicated().any():
        raise ValueError("Pilot candidates require unique nonblank profile_key values")

    frame = candidates.copy()
    frame["clinic_key"] = frame["profile_key"].astype("string").str.strip()
    frame["normalized_zip"] = frame["zip"].map(normalize_zip)
    frame["postal_code_status"] = [
        _postal_code_status(raw, normalized)
        for raw, normalized in zip(frame["zip"], frame["normalized_zip"], strict=True)
    ]
    expected_markets = PILOT_MARKETS if target_markets is None else target_markets
    expected_markets = {str(value).strip() for value in expected_markets}
    if not expected_markets or any(not value for value in expected_markets):
        raise ValueError("Target markets cannot be empty")
    target_requested = set(frame["requested_location"].dropna().astype(str))
    if target_requested != expected_markets:
        raise ValueError(
            f"Candidates must contain exactly {sorted(expected_markets)}"
        )
    zip_lookup = _zip_market_lookup(regions, expected_markets)
    frame["mapped_location"] = frame["normalized_zip"].map(zip_lookup)

    statuses: list[str] = []
    for row in frame.itertuples(index=False):
        if row.postal_code_status == "missing":
            statuses.append("maps_missing_zip")
        elif (
            row.postal_code_status == "us_zip"
            and row.mapped_location == row.requested_location
        ):
            statuses.append("eligible_target_zip")
        else:
            statuses.append("outside_target_zip")
    frame["market_assignment_status"] = statuses
    reviewed = apply_candidate_eligibility_review(frame, category_rules)
    reviewed["provisional_profile_included"] = reviewed[
        "eligibility_review_status"
    ].eq("include_dental_provider")
    return reviewed


def match_reference_locations(
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
    pair_records: list[dict[str, Any]] = []
    reference_records: list[dict[str, Any]] = []
    for ref in reference.itertuples(index=False):
        pool = eligible_zip.loc[
            eligible_zip["mapped_location"].eq(ref.search_location)
        ].copy()
        ref_latitude = _coordinate(ref.latitude, -90, 90)
        ref_longitude = _coordinate(ref.longitude, -180, 180)
        distances = pd.Series(np.nan, index=pool.index, dtype=float)
        valid_coordinates = pool["_latitude"].between(-90, 90) & pool[
            "_longitude"
        ].between(-180, 180)
        if ref_latitude is not None and ref_longitude is not None:
            latitudes = np.radians(pool.loc[valid_coordinates, "_latitude"].to_numpy())
            longitudes = np.radians(
                pool.loc[valid_coordinates, "_longitude"].to_numpy()
            )
            ref_latitude_r = math.radians(ref_latitude)
            ref_longitude_r = math.radians(ref_longitude)
            delta_latitudes = latitudes - ref_latitude_r
            delta_longitudes = longitudes - ref_longitude_r
            haversine = (
                np.sin(delta_latitudes / 2) ** 2
                + math.cos(ref_latitude_r)
                * np.cos(latitudes)
                * np.sin(delta_longitudes / 2) ** 2
            )
            distances.loc[valid_coordinates] = (
                2
                * EARTH_RADIUS_METERS
                * np.arcsin(np.sqrt(np.minimum(1.0, haversine)))
            )
        reference_address = normalize_name(ref.address)
        same_address = (
            pool["_normalized_address"].eq(reference_address)
            if reference_address is not None
            else pd.Series(False, index=pool.index)
        )
        reference_phone = _phone(ref.phone)
        same_phone = (
            pool["_normalized_phone"].eq(reference_phone)
            if reference_phone
            else pd.Series(False, index=pool.index)
        )
        title_similarities = pool["title"].map(
            lambda value: _title_similarity(ref.title, value)
        )
        coordinate_title_match = (
            distances.le(COORDINATE_MATCH_MAX_METERS).fillna(False)
            & title_similarities.ge(TITLE_MATCH_MINIMUM)
        )
        phone_near_match = (
            same_phone & distances.le(PHONE_MATCH_MAX_METERS).fillna(False)
        )
        matched_mask = same_address | coordinate_title_match | phone_near_match
        coordinate_review_mask = (
            distances.le(COORDINATE_MATCH_MAX_METERS).fillna(False)
            & ~matched_mask
        )

        def build_record(candidate_index: Any) -> dict[str, Any]:
            candidate = pool.loc[candidate_index]
            distance_value = distances.loc[candidate_index]
            distance = None if pd.isna(distance_value) else float(distance_value)
            candidate_same_address = bool(same_address.loc[candidate_index])
            candidate_same_phone = bool(same_phone.loc[candidate_index])
            title_similarity = float(title_similarities.loc[candidate_index])
            fixed_rule_match = bool(matched_mask.loc[candidate_index])
            if candidate_same_address:
                matching_evidence = "same_normalized_address"
            elif bool(phone_near_match.loc[candidate_index]):
                matching_evidence = "same_phone_within_100m"
            elif bool(coordinate_title_match.loc[candidate_index]):
                matching_evidence = "within_10m_and_title_similarity_at_least_0p8"
            elif bool(coordinate_review_mask.loc[candidate_index]):
                matching_evidence = "coordinate_only_within_10m_review"
            else:
                matching_evidence = "nearest_candidate_only"
            record = {
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
                "within_10_meters": (
                    distance is not None and distance <= COORDINATE_MATCH_MAX_METERS
                ),
                "title_similarity": round(title_similarity, 4),
                "matching_evidence": matching_evidence,
                "fixed_rule_match": fixed_rule_match,
            }
            return record

        review_records = [
            build_record(index)
            for index in pool.index[matched_mask | coordinate_review_mask]
        ]
        candidates_for_reference = [
            build_record(index) for index in pool.index[matched_mask]
        ]
        pair_records.extend(review_records)
        nearest_record: dict[str, Any] | None = None
        if not pool.empty:
            nearest_index = (
                distances.idxmin() if distances.notna().any() else pool.index[0]
            )
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


def summarize_pilot_comparison(
    reviewed_candidates: pd.DataFrame,
    reference_matches: pd.DataFrame,
    recall_gate: Mapping[str, Any],
    result_log: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return market recall and a compact comparison summary."""

    required_log = {"task_tag", "request_status", "api_cost_usd", "item_count"}
    missing_log = required_log - set(result_log.columns)
    if missing_log:
        raise KeyError(f"Pilot result log is missing columns: {sorted(missing_log)}")
    completed = (
        result_log.loc[result_log["request_status"].eq("completed")]
        .drop_duplicates("task_tag", keep="last")
        .copy()
    )
    if len(completed) != 4:
        raise ValueError("Comparison requires four completed pilot requests")

    recall_input = reference_matches[["reference_key", "market", "discovered"]].copy()
    market_recall, recall_summary = evaluate_pilot_recall(recall_input, recall_gate)
    eligible_recall = float(
        reference_matches["discovered_with_provisional_include"].mean()
    )
    status_counts = reviewed_candidates["eligibility_review_status"].value_counts()
    market_counts = reviewed_candidates.loc[
        reviewed_candidates["market_assignment_status"].eq("eligible_target_zip")
    ]["mapped_location"].value_counts()
    total_cost = pd.to_numeric(completed["api_cost_usd"], errors="raise").sum()
    summary = {
        "analysis_status": "pilot_comparison_before_manual_location_resolution",
        "completed_paid_requests": len(completed),
        "actual_api_cost_usd": round(float(total_cost), 6),
        "raw_items_reported": int(
            pd.to_numeric(completed["item_count"], errors="raise").sum()
        ),
        "unique_profile_candidates": len(reviewed_candidates),
        "eligible_target_zip_profiles": int(
            reviewed_candidates["market_assignment_status"]
            .eq("eligible_target_zip")
            .sum()
        ),
        "outside_target_zip_profiles": int(
            reviewed_candidates["market_assignment_status"]
            .eq("outside_target_zip")
            .sum()
        ),
        "missing_zip_profiles": int(
            reviewed_candidates["market_assignment_status"]
            .eq("maps_missing_zip")
            .sum()
        ),
        "non_us_postal_profiles": int(
            reviewed_candidates["postal_code_status"].eq("non_us_postal").sum()
        ),
        "unrecognized_postal_profiles": int(
            reviewed_candidates["postal_code_status"]
            .eq("unrecognized_postal")
            .sum()
        ),
        "target_zip_share": float(
            reviewed_candidates["market_assignment_status"]
            .eq("eligible_target_zip")
            .mean()
        ),
        "provisional_included_profiles": int(
            status_counts.get("include_dental_provider", 0)
        ),
        "manual_category_review_profiles": int(
            status_counts.get("manual_category_review", 0)
        ),
        "excluded_category_profiles": int(
            status_counts.get("exclude_non_dentist_category", 0)
        ),
        "target_zip_profiles_by_market": {
            str(key): int(value) for key, value in market_counts.sort_index().items()
        },
        "reference_recall": recall_summary,
        "reference_location_count": len(reference_matches),
        "provisional_include_reference_recall": eligible_recall,
        "unmatched_reference_locations": int((~reference_matches["discovered"]).sum()),
        "decision": recall_summary["decision"],
        "manual_work_remaining": [
            "review target-ZIP profiles with manual or excluded primary categories",
            "review duplicate-profile pairs before counting new physical locations",
            "audit unmatched legacy reference locations",
        ],
        "automatic_profile_or_location_merges": 0,
    }
    return market_recall, summary


def summarize_rollout_market_comparison(
    reviewed_candidates: pd.DataFrame,
    reference_matches: pd.DataFrame,
    recall_gate: Mapping[str, Any],
    result_log: pd.DataFrame,
    *,
    market: str,
    reference_universe: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Summarize one rollout market before manual profile-to-location review."""

    required_log = {
        "task_tag",
        "market",
        "request_status",
        "api_cost_usd",
        "item_count",
    }
    missing_log = required_log - set(result_log.columns)
    if missing_log:
        raise KeyError(f"Rollout result log is missing columns: {sorted(missing_log)}")
    clean_market = str(market).strip()
    completed = result_log.loc[
        result_log["request_status"].eq("completed")
        & result_log["market"].astype(str).eq(clean_market)
    ].copy()
    if completed.empty or completed["task_tag"].astype(str).duplicated().any():
        raise ValueError("Rollout market requires unique completed request rows")
    candidate_markets = set(
        reviewed_candidates["requested_location"].dropna().astype(str)
    )
    reference_markets = set(reference_matches["market"].dropna().astype(str))
    if candidate_markets != {clean_market} or reference_markets != {clean_market}:
        raise ValueError("Rollout comparison inputs must contain the selected market only")

    recall_input = reference_matches[["reference_key", "market", "discovered"]].copy()
    market_recall, recall_summary = evaluate_pilot_recall(recall_input, recall_gate)
    status_counts = reviewed_candidates["eligibility_review_status"].value_counts()
    target_zip = reviewed_candidates["market_assignment_status"].eq(
        "eligible_target_zip"
    )
    summary = {
        "analysis_status": "rollout_market_comparison_before_manual_location_resolution",
        "market": clean_market,
        "completed_paid_requests": len(completed),
        "actual_api_cost_usd": round(
            float(pd.to_numeric(completed["api_cost_usd"], errors="raise").sum()),
            6,
        ),
        "raw_items_reported": int(
            pd.to_numeric(completed["item_count"], errors="raise").sum()
        ),
        "unique_profile_candidates": len(reviewed_candidates),
        "eligible_target_zip_profiles": int(target_zip.sum()),
        "outside_target_zip_profiles": int(
            reviewed_candidates["market_assignment_status"]
            .eq("outside_target_zip")
            .sum()
        ),
        "missing_zip_profiles": int(
            reviewed_candidates["market_assignment_status"]
            .eq("maps_missing_zip")
            .sum()
        ),
        "non_us_postal_profiles": int(
            reviewed_candidates["postal_code_status"].eq("non_us_postal").sum()
        ),
        "unrecognized_postal_profiles": int(
            reviewed_candidates["postal_code_status"]
            .eq("unrecognized_postal")
            .sum()
        ),
        "target_zip_share": float(target_zip.mean()),
        "provisional_included_profiles": int(
            status_counts.get("include_dental_provider", 0)
        ),
        "manual_category_review_profiles": int(
            status_counts.get("manual_category_review", 0)
        ),
        "excluded_category_profiles": int(
            status_counts.get("exclude_non_dentist_category", 0)
        ),
        "reference_recall": recall_summary,
        "provisional_include_reference_recall": float(
            reference_matches["discovered_with_provisional_include"].mean()
        ),
        "unmatched_reference_locations": int(
            (~reference_matches["discovered"]).sum()
        ),
        "decision": recall_summary["decision"],
        "manual_work_remaining": [
            "review target-ZIP profiles with manual or excluded primary categories",
            "resolve eligible profiles into physical competition locations",
            "audit unmatched corrected legacy reference locations",
        ],
        "automatic_profile_or_location_merges": 0,
    }
    if reference_universe is not None:
        required_universe = {"search_location", "reference_geography_status"}
        missing_universe = required_universe - set(reference_universe.columns)
        if missing_universe:
            raise KeyError(
                "Reference universe is missing columns: "
                f"{sorted(missing_universe)}"
            )
        universe_markets = set(
            reference_universe["search_location"].dropna().astype(str)
        )
        if universe_markets != {clean_market}:
            raise ValueError("Reference universe must contain the selected market only")
        geography_counts = reference_universe[
            "reference_geography_status"
        ].value_counts()
        eligible_count = int(geography_counts.get("eligible_target_zip", 0))
        if eligible_count != len(reference_matches):
            raise ValueError(
                "Reference matches must contain every target-ZIP reference exactly once"
            )
        summary["legacy_reference_universe"] = {
            "all_competition_units_labeled_as_market": len(reference_universe),
            "eligible_target_zip_units": eligible_count,
            "outside_target_zip_units": int(
                geography_counts.get("outside_target_zip", 0)
            ),
            "missing_zip_units": int(geography_counts.get("missing_zip", 0)),
            "recall_denominator": "eligible_target_zip_units_only",
        }
    return market_recall, summary



