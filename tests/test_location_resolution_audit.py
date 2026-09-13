"""Tests for final profile and physical-location anomaly audits."""

import pandas as pd

from medical_ratings.location_resolution_audit import (
    audit_cross_group_locations,
    audit_profile_anomalies,
)


def row(
    cid: str,
    title: str,
    *,
    address: str,
    latitude: float,
    longitude: float,
    phone: object,
    domain: object,
    votes: object,
    group: str,
) -> dict[str, object]:
    return {
        "clinic_key": f"google:cid:{cid}",
        "cid": cid,
        "title": title,
        "category": "Dentist",
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "phone": phone,
        "domain": domain,
        "votes_count": votes,
        "mapped_location": "Syracuse_NY_M",
        "physical_location_group": group,
    }


def test_profile_audit_flags_non_dental_and_conflicting_evidence() -> None:
    review = pd.DataFrame(
        [
            row(
                "1", "University Pulmonary Associates",
                address="90 Main St, Syracuse, NY 13202",
                latitude=43.05, longitude=-76.15,
                phone="315-555-0100", domain=None, votes=None, group="g1",
            ),
            row(
                "2", "Elvaria Dental Syracuse",
                address="10 Main St, Syracuse, NY 13202",
                latitude=43.06, longitude=-76.16,
                phone=None, domain="heating-air.cloud", votes=None, group="g2",
            ),
            row(
                "3", "Verified Dental",
                address="20 Main St, Syracuse, NY 13202",
                latitude=43.07, longitude=-76.17,
                phone="315-555-0300", domain="verified.example", votes=20,
                group="g3",
            ),
        ]
    )

    anomalies = audit_profile_anomalies(review).set_index("cid")

    assert set(anomalies.index) == {"1", "2"}
    assert anomalies.loc["1", "anomaly_severity"] == "exclude_recommended"
    assert "unrelated_non_dental_business" in anomalies.loc[
        "2", "anomaly_reasons"
    ]


def test_location_audit_flags_nearby_profiles_in_different_groups() -> None:
    review = pd.DataFrame(
        [
            row(
                "1", "Main Dental",
                address="10 Main St Suite 2, Syracuse, NY 13202",
                latitude=43.05000, longitude=-76.15000,
                phone="315-555-0100", domain="main.example", votes=20,
                group="g1",
            ),
            row(
                "2", "Main Dental Old Name",
                address="10 Main St, Syracuse, NY 13202",
                latitude=43.05005, longitude=-76.15005,
                phone="315-555-0200", domain=None, votes=1, group="g2",
            ),
        ]
    )

    pairs = audit_cross_group_locations(review)

    assert len(pairs) == 1
    assert bool(pairs.iloc[0]["same_base_address"])
    assert bool(pairs.iloc[0]["within_30_meters"])


def test_location_audit_ignores_profiles_already_in_same_group() -> None:
    review = pd.DataFrame(
        [
            row(
                "1", "Main Dental",
                address="10 Main St, Syracuse, NY 13202",
                latitude=43.05, longitude=-76.15,
                phone="315-555-0100", domain="main.example", votes=20,
                group="g1",
            ),
            row(
                "2", "Dr Jane Smith DDS",
                address="10 Main St, Syracuse, NY 13202",
                latitude=43.05, longitude=-76.15,
                phone="315-555-0100", domain=None, votes=2, group="g1",
            ),
        ]
    )

    assert audit_cross_group_locations(review).empty
