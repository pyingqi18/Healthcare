from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.business_listings_location_audit import (
    build_business_listings_location_audit,
    prepare_location_audit_candidates,
)


def candidate(
    key: str,
    title: str,
    *,
    address: str,
    phone: str,
    domain: str,
    latitude: float,
    longitude: float,
    included: bool = True,
) -> dict[str, object]:
    return {
        "clinic_key": key,
        "cid": key.rsplit(":", 1)[-1],
        "place_id": f"place-{key}",
        "title": title,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "phone": phone,
        "domain": domain,
        "url": f"https://{domain}" if domain else None,
        "mapped_location": "Syracuse_NY_M",
        "votes_count": 10,
        "observation_count": 1,
        "competition_candidate_included": included,
    }


def candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            candidate(
                "google:cid:1",
                "Main Street Dental",
                address="10 Main St, Syracuse, NY 13202",
                phone="315-555-0100",
                domain="main.example",
                latitude=43.05,
                longitude=-76.15,
            ),
            candidate(
                "google:cid:2",
                "Dr Jane Smith DDS",
                address="10 Main St, Syracuse, NY 13202",
                phone="315-555-0100",
                domain="main.example",
                latitude=43.05001,
                longitude=-76.15001,
            ),
            candidate(
                "google:cid:3",
                "Separate Dental",
                address="900 Other Rd, Syracuse, NY 13210",
                phone="315-555-0300",
                domain="separate.example",
                latitude=43.15,
                longitude=-76.05,
            ),
            candidate(
                "google:cid:4",
                "Excluded Mixed Profile",
                address="10 Main St, Syracuse, NY 13202",
                phone="315-555-0100",
                domain="main.example",
                latitude=43.05,
                longitude=-76.15,
                included=False,
            ),
        ]
    )


def test_adapter_maps_competition_decision_without_changing_source() -> None:
    source = candidates()
    prepared = prepare_location_audit_candidates(source)
    assert "final_included" not in source.columns
    assert prepared["final_included"].tolist() == [True, True, True, False]


def test_adapter_parses_boolean_strings_from_csv() -> None:
    source = candidates()
    source["competition_candidate_included"] = ["True", "true", "1", "False"]
    prepared = prepare_location_audit_candidates(source)
    assert prepared["final_included"].tolist() == [True, True, True, False]


def test_location_audit_outputs_review_blocks_without_automatic_merges() -> None:
    pairs, blocks, summary = build_business_listings_location_audit(candidates())
    assert len(pairs) == 1
    assert len(blocks) == 3
    assert summary["competition_candidate_profiles"] == 3
    assert summary["provisional_review_blocks"] == 2
    assert summary["multi_profile_review_blocks"] == 1
    assert summary["profiles_in_multi_profile_blocks"] == 2
    assert summary["largest_review_block_profiles"] == 2
    assert summary["automatic_profile_or_location_merges"] == 0


def test_location_audit_rejects_duplicate_profile_keys() -> None:
    duplicated = pd.concat([candidates(), candidates().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="unique nonblank"):
        prepare_location_audit_candidates(duplicated)
