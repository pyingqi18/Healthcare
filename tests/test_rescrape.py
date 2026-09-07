"""Unit tests for corrected-location rescrape planning."""

from medical_ratings.rescrape import build_location_rescrape_manifest


def make_regions_config() -> dict[str, object]:
    return {
        "regions": {
            "Malone_NY_S": {
                "location_code": 1023114,
            },
            "Syracuse_NY_M": {
                "location_code": 1023416,
            },
            "Buffalo_NY_L": {
                "location_code": 1022764,
            },
        }
    }


def test_build_location_rescrape_manifest() -> None:
    manifest = build_location_rescrape_manifest(
        make_regions_config(),
        target_regions=["Malone_NY_S", "Syracuse_NY_M"],
        language_code="en",
        depth=100,
    )

    assert len(manifest) == 212
    assert manifest["task_tag"].is_unique

    assert set(manifest["region_key"]) == {
        "Malone_NY_S",
        "Syracuse_NY_M",
    }
    assert set(manifest["location_code"]) == {
        1023114,
        1023416,
    }
    assert not set(manifest["location_code"]) & {
        1026588,
        1027001,
    }

    assert manifest.groupby("region_key").size().to_dict() == {
        "Malone_NY_S": 106,
        "Syracuse_NY_M": 106,
    }
    assert manifest.groupby("api_type").size().to_dict() == {
        "local_finder": 106,
        "maps": 106,
    }
    assert (
        manifest.groupby(["region_key", "api_type"])
        .size()
        .eq(53)
        .all()
    )
    assert set(manifest["language_code"]) == {"en"}
    assert set(manifest["depth"]) == {100}


def test_build_location_rescrape_manifest_rejects_unknown_region() -> None:
    try:
        build_location_rescrape_manifest(
            make_regions_config(),
            target_regions=["Unknown_NY_S"],
            language_code="en",
            depth=100,
        )
    except KeyError as error:
        assert "Unknown_NY_S" in str(error)
    else:
        raise AssertionError("Unknown region was accepted")
