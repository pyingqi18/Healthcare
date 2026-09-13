"""Tests for duplicate-profile candidate pair generation."""

import pandas as pd

from medical_ratings.duplicate_candidate_audit import (
    build_duplicate_candidate_pairs,
)


def row(
    cid: str,
    title: str,
    *,
    address: str,
    latitude: float,
    longitude: float,
    phone: str,
    domain: str,
    market: str = "Syracuse_NY_M",
    included: bool = True,
) -> dict[str, object]:
    return {
        "clinic_key": f"google:cid:{cid}",
        "cid": cid,
        "title": title,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "phone": phone,
        "domain": domain,
        "url": f"https://{domain}",
        "mapped_location": market,
        "final_included": included,
    }


def test_duplicate_audit_flags_shared_identity_evidence() -> None:
    candidates = pd.DataFrame(
        [
            row(
                "1",
                "Northside Dental",
                address="10 Main St, Syracuse, NY 13202",
                latitude=43.05000,
                longitude=-76.15000,
                phone="+1 (315) 555-0100",
                domain="www.northside.example",
            ),
            row(
                "2",
                "Northside Dental PLLC",
                address="10 Main Street, Syracuse, NY 13202",
                latitude=43.05005,
                longitude=-76.15005,
                phone="315-555-0100",
                domain="northside.example",
            ),
            row(
                "3",
                "Unrelated Dental",
                address="900 Other Rd, Syracuse, NY 13210",
                latitude=43.10000,
                longitude=-76.10000,
                phone="315-555-0300",
                domain="unrelated.example",
            ),
        ]
    )

    pairs = build_duplicate_candidate_pairs(candidates)

    assert len(pairs) == 1
    pair = pairs.iloc[0]
    assert bool(pair["same_phone"])
    assert bool(pair["same_domain"])
    assert bool(pair["within_50_meters"])
    assert pair["review_priority"] == "high"
    assert pair["review_decision"] == "pending_manual_review"


def test_duplicate_audit_does_not_pair_excluded_or_cross_market_rows() -> None:
    candidates = pd.DataFrame(
        [
            row(
                "1",
                "Shared Dental",
                address="10 Main St, Syracuse, NY 13202",
                latitude=43.05,
                longitude=-76.15,
                phone="315-555-0100",
                domain="shared.example",
            ),
            row(
                "2",
                "Shared Dental Malone",
                address="10 Main St, Malone, NY 12953",
                latitude=44.85,
                longitude=-74.29,
                phone="315-555-0100",
                domain="shared.example",
                market="Malone_NY_S",
            ),
            row(
                "3",
                "Excluded Shared Dental",
                address="10 Main St, Syracuse, NY 13202",
                latitude=43.05,
                longitude=-76.15,
                phone="315-555-0100",
                domain="shared.example",
                included=False,
            ),
        ]
    )

    pairs = build_duplicate_candidate_pairs(candidates)

    assert pairs.empty


def test_duplicate_audit_rejects_weak_shared_contact_signal() -> None:
    candidates = pd.DataFrame(
        [
            row(
                "1",
                "Doctor One",
                address="10 Main St, Syracuse, NY 13202",
                latitude=43.05,
                longitude=-76.15,
                phone="315-555-0100",
                domain="group.example",
            ),
            row(
                "2",
                "Completely Different Practice",
                address="900 Other Rd, Syracuse, NY 13210",
                latitude=43.15,
                longitude=-76.05,
                phone="315-555-0200",
                domain="group.example",
            ),
        ]
    )

    pairs = build_duplicate_candidate_pairs(candidates)

    assert pairs.empty


def test_duplicate_audit_rejects_duplicate_input_keys() -> None:
    candidate = row(
        "1",
        "Dental One",
        address="10 Main St, Syracuse, NY 13202",
        latitude=43.05,
        longitude=-76.15,
        phone="315-555-0100",
        domain="one.example",
    )
    candidates = pd.DataFrame([candidate, candidate])

    try:
        build_duplicate_candidate_pairs(candidates)
    except ValueError as error:
        assert "duplicate clinic_key" in str(error)
    else:
        raise AssertionError("Expected duplicate clinic keys to fail")
