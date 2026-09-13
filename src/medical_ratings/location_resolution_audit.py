"""Audit false-positive profiles and physical-location split candidates."""

from __future__ import annotations

from difflib import SequenceMatcher
import math
import re
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from medical_ratings.identifiers import normalize_name


REQUIRED_COLUMNS = {
    "clinic_key",
    "cid",
    "title",
    "category",
    "address",
    "latitude",
    "longitude",
    "phone",
    "domain",
    "votes_count",
    "mapped_location",
    "physical_location_group",
}
NON_DENTAL_TITLE_PATTERN = re.compile(r"\b(?:pulmonary|ddso)\b", re.I)
NON_DENTAL_DOMAIN_PATTERN = re.compile(
    r"(?:heating|hvac|plumb|roof|air[-_]?condition)", re.I
)
GENERIC_DENTAL_PATTERN = re.compile(
    r"\b(?:dentist|dental|dentistry|smile|implant)\b", re.I
)
PERSON_PATTERN = re.compile(r"(?:^|\W)(?:dr|dds|dmd|bds)(?:\W|$)", re.I)
MARKET_AREA_CODES = {
    "Malone_NY_S": {"518", "838"},
    "Syracuse_NY_M": {"315", "680"},
}
TOLL_FREE_AREA_CODES = {"800", "833", "844", "855", "866", "877", "888"}
EARTH_RADIUS_METERS = 6_371_008.8


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
    return host.removeprefix("www.") or None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _base_address(value: Any) -> str | None:
    normalized = normalize_name(value)
    if normalized is None:
        return None
    normalized = re.split(
        r"\b(?:suite|ste|unit|room|rm|floor|fl)\b|\s#\s*\w+",
        normalized,
        maxsplit=1,
    )[0]
    normalized = re.split(
        r"\b(?:syracuse|solvay|north syracuse|de witt|malone)\b",
        normalized,
        maxsplit=1,
    )[0]
    return normalized.strip() or None


def _distance_meters(left: pd.Series, right: pd.Series) -> float | None:
    values = [
        _number(left["latitude"]),
        _number(left["longitude"]),
        _number(right["latitude"]),
        _number(right["longitude"]),
    ]
    if any(value is None for value in values):
        return None
    lat_1, lon_1, lat_2, lon_2 = map(math.radians, values)
    delta_latitude = lat_2 - lat_1
    delta_longitude = lon_2 - lon_1
    value = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(lat_1)
        * math.cos(lat_2)
        * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(min(1.0, value)))


def audit_profile_anomalies(review: pd.DataFrame) -> pd.DataFrame:
    """Return profiles needing evidence review before final inclusion."""

    missing = REQUIRED_COLUMNS - set(review.columns)
    if missing:
        raise KeyError(f"Review table is missing columns: {sorted(missing)}")
    records: list[dict[str, Any]] = []

    for _, row in review.iterrows():
        title = _text(row["title"]) or ""
        address = _text(row["address"]) or ""
        domain = _domain(row["domain"])
        phone = _phone(row["phone"])
        votes = _number(row["votes_count"])
        reasons: list[str] = []
        severity = "manual_review"

        if NON_DENTAL_TITLE_PATTERN.search(title):
            reasons.append("title_contains_non_dental_service_or_agency_term")
            severity = "exclude_recommended"
        if (
            "albany" in title.casefold()
            and "syracuse" in address.casefold()
        ):
            reasons.append("title_market_conflicts_with_address")
            severity = "exclude_recommended"
        if domain is not None and NON_DENTAL_DOMAIN_PATTERN.search(domain):
            reasons.append("domain_indicates_unrelated_non_dental_business")
            severity = "exclude_recommended"

        market_codes = MARKET_AREA_CODES.get(str(row["mapped_location"]), set())
        if phone is not None:
            area_code = phone[:3]
            if (
                market_codes
                and area_code not in market_codes
                and area_code not in TOLL_FREE_AREA_CODES
                and (votes is None or votes <= 1)
            ):
                reasons.append("low_evidence_listing_uses_nonlocal_phone")

        generic_title = bool(GENERIC_DENTAL_PATTERN.search(title))
        person_title = bool(PERSON_PATTERN.search(title))
        if (
            generic_title
            and not person_title
            and phone is None
            and domain is None
            and votes is None
        ):
            reasons.append("generic_listing_has_no_phone_domain_or_reviews")

        if not reasons:
            continue
        record = row.to_dict()
        record["anomaly_severity"] = severity
        record["anomaly_reasons"] = "|".join(reasons)
        record["anomaly_review_decision"] = "pending_manual_review"
        records.append(record)

    return pd.DataFrame.from_records(records)


def audit_cross_group_locations(review: pd.DataFrame) -> pd.DataFrame:
    """Return colocated profile pairs assigned to different location groups."""

    missing = REQUIRED_COLUMNS - set(review.columns)
    if missing:
        raise KeyError(f"Review table is missing columns: {sorted(missing)}")
    frame = review.sort_values("clinic_key").reset_index(drop=True)
    records: list[dict[str, Any]] = []

    for left_index in range(len(frame)):
        left = frame.iloc[left_index]
        for right_index in range(left_index + 1, len(frame)):
            right = frame.iloc[right_index]
            if left["mapped_location"] != right["mapped_location"]:
                continue
            if left["physical_location_group"] == right["physical_location_group"]:
                continue
            left_base = _base_address(left["address"])
            right_base = _base_address(right["address"])
            same_base_address = (
                left_base is not None and left_base == right_base
            )
            distance = _distance_meters(left, right)
            within_30_meters = distance is not None and distance <= 30
            if not same_base_address and not within_30_meters:
                continue

            left_phone = _phone(left["phone"])
            right_phone = _phone(right["phone"])
            left_domain = _domain(left["domain"])
            right_domain = _domain(right["domain"])
            left_title = normalize_name(left["title"]) or ""
            right_title = normalize_name(right["title"]) or ""
            similarity = SequenceMatcher(None, left_title, right_title).ratio()
            records.append(
                {
                    "left_clinic_key": left["clinic_key"],
                    "left_cid": left["cid"],
                    "left_title": left["title"],
                    "left_address": left["address"],
                    "left_location_group": left["physical_location_group"],
                    "right_clinic_key": right["clinic_key"],
                    "right_cid": right["cid"],
                    "right_title": right["title"],
                    "right_address": right["address"],
                    "right_location_group": right["physical_location_group"],
                    "mapped_location": left["mapped_location"],
                    "same_base_address": same_base_address,
                    "within_30_meters": within_30_meters,
                    "distance_meters": (
                        None if distance is None else round(distance, 1)
                    ),
                    "same_phone": (
                        left_phone is not None and left_phone == right_phone
                    ),
                    "same_domain": (
                        left_domain is not None and left_domain == right_domain
                    ),
                    "title_similarity": round(similarity, 4),
                    "location_review_decision": "pending_manual_review",
                }
            )

    return pd.DataFrame.from_records(records)
