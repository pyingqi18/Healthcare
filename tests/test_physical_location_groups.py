"""Tests for physical dental-location grouping suggestions."""

import pandas as pd

from medical_ratings.physical_location_groups import (
    build_physical_location_review,
)


def candidate(
    cid: str,
    title: str,
    *,
    votes: int,
    market: str = "Syracuse_NY_M",
    included: bool = True,
) -> dict[str, object]:
    return {
        "clinic_key": f"google:cid:{cid}",
        "cid": cid,
        "title": title,
        "mapped_location": market,
        "votes_count": votes,
        "observation_count": 5,
        "address": "10 Main St, Syracuse, NY 13202",
        "phone": "315-555-0100",
        "domain": "clinic.example",
        "final_included": included,
    }


def pair(
    left: str,
    right: str,
    *,
    same_phone: bool,
    same_domain: bool,
    same_address: bool,
    within_50: bool,
    similarity: float,
) -> dict[str, object]:
    return {
        "left_clinic_key": f"google:cid:{left}",
        "right_clinic_key": f"google:cid:{right}",
        "same_phone": same_phone,
        "same_domain": same_domain,
        "same_address": same_address,
        "within_50_meters": within_50,
        "title_similarity": similarity,
    }


def test_location_group_prefers_organization_over_provider_profile() -> None:
    candidates = pd.DataFrame(
        [
            candidate("1", "Dr. Jane Smith, DDS", votes=80),
            candidate("2", "Main Street Dental", votes=25),
            candidate("3", "Independent Dental", votes=40),
        ]
    )
    pairs = pd.DataFrame(
        [
            pair(
                "1", "2", same_phone=True, same_domain=True,
                same_address=True, within_50=True, similarity=0.2,
            )
        ]
    )

    review = build_physical_location_review(candidates, pairs).set_index(
        "clinic_key"
    )

    assert review.loc["google:cid:1", "location_group_size"] == 2
    assert not bool(
        review.loc["google:cid:1", "suggested_canonical_profile"]
    )
    assert bool(review.loc["google:cid:2", "suggested_canonical_profile"])
    assert review.loc["google:cid:2", "profile_role"] == "organization"
    assert review.loc["google:cid:3", "location_group_size"] == 1


def test_location_group_does_not_merge_chain_on_weak_domain_only_edge() -> None:
    candidates = pd.DataFrame(
        [
            candidate("1", "First Dental", votes=20),
            candidate("2", "Second Dental", votes=30),
            candidate("3", "Third Dental", votes=40),
        ]
    )
    pairs = pd.DataFrame(
        [
            pair(
                "1", "2", same_phone=True, same_domain=True,
                same_address=True, within_50=True, similarity=0.5,
            ),
            pair(
                "2", "3", same_phone=False, same_domain=True,
                same_address=False, within_50=False, similarity=0.6,
            ),
        ]
    )

    review = build_physical_location_review(candidates, pairs).set_index(
        "clinic_key"
    )

    assert review.loc["google:cid:1", "physical_location_group"] == (
        review.loc["google:cid:2", "physical_location_group"]
    )
    assert review.loc["google:cid:3", "physical_location_group"] != (
        review.loc["google:cid:2", "physical_location_group"]
    )


def test_location_group_uses_reviews_when_no_organization_profile_exists() -> None:
    candidates = pd.DataFrame(
        [
            candidate("1", "Jane Smith", votes=0),
            candidate("2", "Jane Smith DDS", votes=12),
        ]
    )
    pairs = pd.DataFrame(
        [
            pair(
                "1", "2", same_phone=True, same_domain=True,
                same_address=True, within_50=True, similarity=0.8,
            )
        ]
    )

    review = build_physical_location_review(candidates, pairs).set_index(
        "clinic_key"
    )

    assert bool(review.loc["google:cid:2", "suggested_canonical_profile"])


def test_location_group_accepts_nearby_shared_phone_without_shared_domain() -> None:
    candidates = pd.DataFrame(
        [
            candidate("1", "Main Dental", votes=20),
            candidate("2", "Jane Smith DDS", votes=5),
        ]
    )
    pairs = pd.DataFrame(
        [
            pair(
                "1", "2", same_phone=True, same_domain=False,
                same_address=False, within_50=True, similarity=0.2,
            )
        ]
    )

    review = build_physical_location_review(candidates, pairs)

    assert review["physical_location_group"].nunique() == 1
    assert set(review["location_group_size"]) == {2}


def test_location_group_excludes_nonfinal_candidates() -> None:
    candidates = pd.DataFrame(
        [
            candidate("1", "Included Dental", votes=10),
            candidate("2", "Excluded Dental", votes=10, included=False),
        ]
    )
    pairs = pd.DataFrame(
        columns=[
            "left_clinic_key",
            "right_clinic_key",
            "same_phone",
            "same_domain",
            "same_address",
            "within_50_meters",
            "title_similarity",
        ]
    )

    review = build_physical_location_review(candidates, pairs)

    assert list(review["clinic_key"]) == ["google:cid:1"]
    assert review.iloc[0]["location_review_status"] == (
        "singleton_no_review_needed"
    )
