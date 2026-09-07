"""Stable provider and clinic-location identifier helpers."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Mapping
from typing import Any


def normalize_zip(value: Any) -> str | None:
    """Return a normalized five-digit ZIP code or None."""

    if value is None:
        return None

    try:
        if bool(math.isnan(value)):
            return None
    except (TypeError, ValueError):
        pass

    text = str(value).strip()

    if not text:
        return None

    if re.search(r"[A-Za-z]", text):
        return None

    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", maxsplit=1)[0]

    base_zip = text.split("-", maxsplit=1)[0]
    digits = re.sub(r"\D", "", base_zip)

    if not digits:
        return None

    return digits[:5].zfill(5)


def normalize_name(value: Any) -> str | None:
    """Normalize a public business or provider name."""

    if value is None:
        return None

    try:
        if bool(math.isnan(value)):
            return None
    except (TypeError, ValueError):
        pass

    text = str(value).strip()

    if (
        not text
        or text.lower() in {
            "nan",
            "none",
            "<na>",
        }
    ):
        return None

    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode()
    )

    text = re.sub(
        r"[^a-zA-Z0-9]+",
        " ",
        text.lower(),
    ).strip()

    text = re.sub(r"\s+", " ", text)

    return text or None


def _coordinate_token(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return ""
    if math.isnan(numeric):
        return ""
    return f"{numeric:.5f}"


def build_clinic_key(record: Mapping[str, Any]) -> str:
    """Build a deterministic clinic-location key using the best available identifier."""

    for field in ("place_id", "cid"):
        value = record.get(field)
        if value not in (None, ""):
            return f"google:{field}:{value}"

    normalized_name = normalize_name(record.get("title") or record.get("name")) or ""
    zip_code = normalize_zip(record.get("zip")) or ""
    latitude = _coordinate_token(record.get("latitude"))
    longitude = _coordinate_token(record.get("longitude"))
    npi = str(record.get("NPI") or record.get("npi") or "").strip()

    if not normalized_name and not npi:
        raise ValueError("A clinic key requires a stable Google ID, provider name, or NPI")

    payload = "|".join([npi, normalized_name, zip_code, latitude, longitude])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"fallback:{digest}"
