"""Geographic validation for collected clinic records."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


def normalize_location_code(
    value: Any,
) -> str | None:
    """Normalize a location code read from CSV."""

    if value is None:
        return None

    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass

    text = str(value).strip()

    if not text:
        return None

    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", maxsplit=1)[0]

    if not text.isdigit():
        return None

    return text


def add_location_code_status(
    clinics: pd.DataFrame,
    regions: dict,
) -> pd.DataFrame:
    """Compare collected and expected location codes."""

    required_columns = {
        "search_location",
        "used_location_code",
    }
    missing_columns = (
        required_columns - set(clinics.columns)
    )

    if missing_columns:
        raise KeyError(
            "Missing clinic columns: "
            f"{sorted(missing_columns)}"
        )

    expected_codes = {
        location: normalize_location_code(
            details.get("location_code")
        )
        for location, details in regions.items()
    }

    result = clinics.copy()

    result["expected_location_code"] = (
        result["search_location"]
        .map(expected_codes)
        .astype("string")
    )

    result["used_location_code_normalized"] = (
        result["used_location_code"]
        .map(normalize_location_code)
        .astype("string")
    )

    unknown_location = (
        result["expected_location_code"].isna()
    )
    missing_used_code = (
        result[
            "used_location_code_normalized"
        ].isna()
    )
    mismatched_code = (
        ~unknown_location
        & ~missing_used_code
        & (
            result[
                "used_location_code_normalized"
            ]
            != result["expected_location_code"]
        )
    )

    status = pd.Series(
        "valid_location_code",
        index=result.index,
        dtype="string",
    )

    status.loc[unknown_location] = (
        "unknown_search_location"
    )
    status.loc[
        ~unknown_location & missing_used_code
    ] = "missing_location_code"
    status.loc[mismatched_code] = (
        "location_code_mismatch"
    )

    result["location_code_status"] = status
    result["analysis_location_eligible"] = (
        status == "valid_location_code"
    )

    return result
def add_analysis_eligibility(
    clinics: pd.DataFrame,
    regions: dict,
) -> pd.DataFrame:
    """Add preliminary analysis eligibility flags."""

    if "zip" not in clinics.columns:
        raise KeyError(
            "Missing clinic column: zip"
        )

    result = add_location_code_status(
        clinics,
        regions,
    )

    raw_postal = (
        result["zip"]
        .astype("string")
        .str.strip()
    )

    non_us_postal = raw_postal.str.contains(
        r"[A-Za-z]",
        regex=True,
        na=False,
    )

    exclusion_reason = pd.Series(
        "eligible",
        index=result.index,
        dtype="string",
    )

    invalid_location_code = (
        result["location_code_status"]
        != "valid_location_code"
    )

    exclusion_reason.loc[
        invalid_location_code
    ] = result.loc[
        invalid_location_code,
        "location_code_status",
    ]

    exclusion_reason.loc[
        ~invalid_location_code
        & non_us_postal
    ] = "non_us_postal"

    result["analysis_exclusion_reason"] = (
        exclusion_reason
    )
    result["preliminary_analysis_eligible"] = (
        exclusion_reason == "eligible"
    )

    return result