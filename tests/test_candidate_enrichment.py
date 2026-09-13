"""Tests for exact-CID Business Info candidate enrichment."""

import pandas as pd

from medical_ratings.candidate_enrichment import (
    enrich_candidates_with_business_info,
)


def candidate(cid: str, requested: str) -> dict[str, object]:
    return {
        "clinic_key": f"google:cid:{cid}",
        "cid": cid,
        "place_id": None,
        "title": f"Search title {cid}",
        "category": None,
        "address": None,
        "zip": None,
        "latitude": None,
        "longitude": None,
        "phone": None,
        "domain": None,
        "url": None,
        "rating_value": None,
        "votes_count": None,
        "result_datetime_utc": None,
        "requested_locations": requested,
        "market_assignment_status": "local_finder_only_unlocated",
        "eligibility_review_status": "needs_geography",
    }


def profile(
    cid: str,
    *,
    address: str,
    zip_value: object,
    country_code: object,
) -> dict[str, object]:
    return {
        "task_id": f"task-{cid}",
        "cid": cid,
        "place_id": f"place-{cid}",
        "title": f"Profile title {cid}",
        "category": "Dentist",
        "address": address,
        "zip": zip_value,
        "country_code": country_code,
        "latitude": 43.0,
        "longitude": -76.0,
        "phone": "555-0100",
        "domain": "example.com",
        "url": "https://example.com",
        "rating_value": 4.5,
        "votes_count": 20,
        "result_datetime_utc": "2026-09-08 03:00:00 +00:00",
    }


def test_enrichment_resolves_us_address_zip_and_excludes_canada() -> None:
    candidates = pd.DataFrame(
        [
            candidate("1", "Syracuse_NY_M"),
            candidate("2", "Malone_NY_S"),
        ]
    )
    profiles = pd.DataFrame(
        [
            profile(
                "1",
                address="Solvay, NY 13219",
                zip_value=None,
                country_code="US",
            ),
            profile(
                "2",
                address="Montreal, Quebec H3Z 1E6, Canada",
                zip_value="H3Z 1E6",
                country_code="CA",
            ),
        ]
    )
    regions = {
        "Malone_NY_S": {"zip_values": [12953]},
        "Syracuse_NY_M": {"zip_ranges": [[13200, 13299]]},
    }

    enriched = enrich_candidates_with_business_info(
        candidates, profiles, regions
    ).set_index("cid")

    assert enriched.loc["1", "zip"] == "13219"
    assert enriched.loc["1", "mapped_location"] == "Syracuse_NY_M"
    assert enriched.loc["1", "market_assignment_status"] == (
        "eligible_target_zip"
    )
    assert enriched.loc["1", "title"] == "Profile title 1"
    assert enriched.loc["1", "search_title"] == "Search title 1"
    assert enriched.loc["2", "market_assignment_status"] == (
        "outside_target_zip"
    )


def test_enrichment_requires_complete_needs_geography_profile_coverage() -> None:
    candidates = pd.DataFrame([candidate("1", "Syracuse_NY_M")])
    unrelated_profile = pd.DataFrame(
        [
            profile(
                "2",
                address="1 Main St, Syracuse, NY 13202",
                zip_value="13202",
                country_code="US",
            )
        ]
    )
    regions = {"Syracuse_NY_M": {"zip_ranges": [[13200, 13299]]}}

    try:
        enrich_candidates_with_business_info(
            candidates, unrelated_profile, regions
        )
    except ValueError as error:
        assert "coverage does not match" in str(error)
    else:
        raise AssertionError("Expected incomplete profile coverage to fail")
