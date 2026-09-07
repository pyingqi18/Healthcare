"""Tests for geographic collection validation."""

from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.geography import (
    add_analysis_eligibility,
    add_location_code_status,
    normalize_location_code,
)


REGIONS_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "regions.yaml"
)


def load_regions() -> dict:
    with REGIONS_PATH.open(
        "r",
        encoding="utf-8",
    ) as stream:
        return yaml.safe_load(stream)["regions"]


def test_normalize_location_code() -> None:
    assert normalize_location_code(
        1023416.0
    ) == "1023416"
    assert normalize_location_code(
        "1023416.0"
    ) == "1023416"
    assert normalize_location_code(
        "1023416"
    ) == "1023416"
    assert normalize_location_code(None) is None
    assert normalize_location_code(pd.NA) is None


def test_all_regions_have_unique_location_codes() -> None:
    regions = load_regions()

    assert len(regions) == 15

    codes = [
        region.get("location_code")
        for region in regions.values()
    ]

    assert all(code is not None for code in codes)
    assert len(codes) == len(set(codes))

    assert (
        regions["Malone_NY_S"]["location_code"]
        == 1023114
    )
    assert (
        regions["Syracuse_NY_M"][
            "location_code"
        ]
        == 1023416
    )


def test_add_location_code_status() -> None:
    clinics = pd.DataFrame(
        {
            "search_location": [
                "Syracuse_NY_M",
                "Syracuse_NY_M",
                "Malone_NY_S",
                "Buffalo_NY_L",
                "Unknown_Place",
            ],
            "used_location_code": [
                1023416.0,
                1027001.0,
                1026588.0,
                1022764.0,
                None,
            ],
        }
    )

    result = add_location_code_status(
        clinics,
        load_regions(),
    )

    assert result[
        "location_code_status"
    ].tolist() == [
        "valid_location_code",
        "location_code_mismatch",
        "location_code_mismatch",
        "valid_location_code",
        "unknown_search_location",
    ]

    assert result[
        "analysis_location_eligible"
    ].tolist() == [
        True,
        False,
        False,
        True,
        False,
    ]

def test_add_analysis_eligibility() -> None:
    clinics = pd.DataFrame(
        {
            "search_location": [
                "Syracuse_NY_M",
                "Syracuse_NY_M",
                "Buffalo_NY_L",
                "Buffalo_NY_L",
            ],
            "used_location_code": [
                1023416,
                1027001,
                1022764,
                1022764,
            ],
            "zip": [
                "13202",
                "84015",
                "L2A 2S7",
                None,
            ],
        }
    )

    result = add_analysis_eligibility(
        clinics,
        load_regions(),
    )

    assert result[
        "analysis_exclusion_reason"
    ].tolist() == [
        "eligible",
        "location_code_mismatch",
        "non_us_postal",
        "eligible",
    ]

    assert result[
        "preliminary_analysis_eligible"
    ].tolist() == [
        True,
        False,
        False,
        True,
    ]
