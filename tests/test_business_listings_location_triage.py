from __future__ import annotations

import pandas as pd

from medical_ratings.business_listings_location_triage import triage_location_blocks


def profile(
    key: str,
    group: str,
    title: str,
    *,
    address: str,
    phone: str,
    domain: str,
    latitude: float,
    longitude: float,
    role: str,
    canonical: bool = False,
) -> dict[str, object]:
    return {
        "clinic_key": key,
        "physical_location_group": group,
        "location_group_size": 2,
        "mapped_location": "Syracuse_NY_M",
        "title": title,
        "address": address,
        "phone": phone,
        "domain": domain,
        "latitude": latitude,
        "longitude": longitude,
        "profile_role": role,
        "suggested_canonical_profile": canonical,
    }


def pair(
    left: str,
    right: str,
    *,
    same_phone: bool,
    same_domain: bool,
    same_address: bool,
    within_50: bool,
) -> dict[str, object]:
    return {
        "left_clinic_key": left,
        "right_clinic_key": right,
        "same_phone": same_phone,
        "same_domain": same_domain,
        "same_address": same_address,
        "within_50_meters": within_50,
        "title_similarity": 0.6,
    }


def test_triage_marks_dense_shared_identity_as_routine() -> None:
    blocks = pd.DataFrame(
        [
            profile("1", "g1", "Main Dental", address="10 Main St", phone="3155550100", domain="main.example", latitude=43.0, longitude=-76.0, role="organization", canonical=True),
            profile("2", "g1", "Jane Smith DDS", address="10 Main St Suite 1", phone="3155550100", domain="main.example", latitude=43.00001, longitude=-76.00001, role="individual_provider"),
        ]
    )
    pairs = pd.DataFrame([pair("1", "2", same_phone=True, same_domain=True, same_address=False, within_50=True)])
    summary, profiles, metadata = triage_location_blocks(blocks, pairs)
    assert summary.iloc[0]["review_tier"] == "routine_shared_identity"
    assert len(profiles) == 2
    assert metadata["automatic_profile_or_location_merges"] == 0


def test_triage_marks_multiple_base_addresses_as_complex() -> None:
    blocks = pd.DataFrame(
        [
            profile("1", "g1", "Dental Group", address="10 Main St", phone="3155550100", domain="group.example", latitude=43.0, longitude=-76.0, role="organization", canonical=True),
            profile("2", "g1", "Dental Group East", address="900 Other Rd", phone="3155550100", domain="group.example", latitude=43.00001, longitude=-76.00001, role="organization"),
        ]
    )
    pairs = pd.DataFrame([pair("1", "2", same_phone=True, same_domain=True, same_address=False, within_50=True)])
    summary, _, _ = triage_location_blocks(blocks, pairs)
    assert summary.iloc[0]["review_tier"] == "complex_review"
    assert "multiple base addresses" in summary.iloc[0]["review_reason"]


def test_triage_preserves_singletons_outside_manual_queue() -> None:
    blocks = pd.DataFrame(
        [
            profile("1", "g1", "Main Dental", address="10 Main St", phone="3155550100", domain="main.example", latitude=43.0, longitude=-76.0, role="organization", canonical=True),
            profile("2", "g1", "Jane Smith DDS", address="10 Main St", phone="3155550100", domain="main.example", latitude=43.0, longitude=-76.0, role="individual_provider"),
            {**profile("3", "g2", "Solo Dental", address="20 Main St", phone="3155550200", domain="solo.example", latitude=43.1, longitude=-76.1, role="organization", canonical=True), "location_group_size": 1},
        ]
    )
    pairs = pd.DataFrame([pair("1", "2", same_phone=True, same_domain=True, same_address=True, within_50=True)])
    summary, profiles, metadata = triage_location_blocks(blocks, pairs)
    assert len(summary) == 1
    assert set(profiles["clinic_key"]) == {"1", "2"}
    assert metadata["multi_profile_review_blocks"] == 1

