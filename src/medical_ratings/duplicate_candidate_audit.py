"""Build review pairs for possible duplicate Google clinic profiles."""

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
    "address",
    "latitude",
    "longitude",
    "phone",
    "domain",
    "url",
    "mapped_location",
    "final_included",
}
EARTH_RADIUS_METERS = 6_371_008.8


def _text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    value = str(value).strip()
    return value or None


def _phone(value: Any) -> str | None:
    value = _text(value)
    if value is None:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def _domain(domain: Any, url: Any) -> str | None:
    value = _text(domain) or _text(url)
    if value is None:
        return None
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = (parsed.hostname or "").casefold().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


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


def _similarity(left: Any, right: Any) -> float:
    left_name = normalize_name(left)
    right_name = normalize_name(right)
    if left_name is None or right_name is None:
        return 0.0
    return SequenceMatcher(None, left_name, right_name).ratio()


def build_duplicate_candidate_pairs(candidates: pd.DataFrame) -> pd.DataFrame:
    """Return deterministic review pairs; no candidate is merged or removed."""

    missing = REQUIRED_COLUMNS - set(candidates.columns)
    if missing:
        raise KeyError(f"Candidates are missing columns: {sorted(missing)}")
    if candidates.empty:
        raise ValueError("Candidates table is empty")
    if candidates["clinic_key"].isna().any():
        raise ValueError("Candidates contain missing clinic_key values")
    if candidates["clinic_key"].duplicated().any():
        raise ValueError("Candidates contain duplicate clinic_key values")

    included = candidates.loc[candidates["final_included"].astype(bool)].copy()
    included = included.sort_values("clinic_key").reset_index(drop=True)
    records: list[dict[str, Any]] = []

    for left_index in range(len(included)):
        left = included.iloc[left_index]
        for right_index in range(left_index + 1, len(included)):
            right = included.iloc[right_index]
            if _text(left["mapped_location"]) != _text(right["mapped_location"]):
                continue

            left_phone = _phone(left["phone"])
            right_phone = _phone(right["phone"])
            left_domain = _domain(left["domain"], left["url"])
            right_domain = _domain(right["domain"], right["url"])
            left_address = normalize_name(left["address"])
            right_address = normalize_name(right["address"])
            same_phone = left_phone is not None and left_phone == right_phone
            same_domain = left_domain is not None and left_domain == right_domain
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

            evidence_count = sum(
                (same_phone, same_domain, same_address, close_50m)
            )
            high_priority = (
                (same_address or close_50m)
                and (same_phone or same_domain or title_similarity >= 0.55)
            ) or (
                same_phone and same_domain and title_similarity >= 0.40
            )
            records.append(
                {
                    "left_clinic_key": left["clinic_key"],
                    "left_cid": left["cid"],
                    "left_title": left["title"],
                    "left_address": left["address"],
                    "right_clinic_key": right["clinic_key"],
                    "right_cid": right["cid"],
                    "right_title": right["title"],
                    "right_address": right["address"],
                    "mapped_location": left["mapped_location"],
                    "same_phone": same_phone,
                    "same_domain": same_domain,
                    "same_address": same_address,
                    "within_50_meters": close_50m,
                    "distance_meters": (
                        None if distance is None else round(distance, 1)
                    ),
                    "title_similarity": round(title_similarity, 4),
                    "evidence_count": evidence_count,
                    "review_priority": "high" if high_priority else "standard",
                    "review_decision": "pending_manual_review",
                }
            )

    columns = [
        "left_clinic_key",
        "left_cid",
        "left_title",
        "left_address",
        "right_clinic_key",
        "right_cid",
        "right_title",
        "right_address",
        "mapped_location",
        "same_phone",
        "same_domain",
        "same_address",
        "within_50_meters",
        "distance_meters",
        "title_similarity",
        "evidence_count",
        "review_priority",
        "review_decision",
    ]
    return pd.DataFrame.from_records(records, columns=columns)
