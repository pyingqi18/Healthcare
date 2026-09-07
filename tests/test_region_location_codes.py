"""Regression tests for corrected geographic location codes."""

from pathlib import Path

import yaml


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


def test_correct_new_york_location_codes() -> None:
    regions = load_regions()

    assert (
        regions["Malone_NY_S"]["location_code"]
        == 1023114
    )
    assert (
        regions["Syracuse_NY_M"]["location_code"]
        == 1023416
    )


def test_wrong_same_name_location_codes_are_not_used() -> None:
    regions = load_regions()

    configured_codes = {
        region["location_code"]
        for region in regions.values()
        if "location_code" in region
    }

    assert 1026588 not in configured_codes
    assert 1027001 not in configured_codes