"""Tests for Maps core deduplication, keyword overlap, and category groups."""

from __future__ import annotations

import json

import pandas as pd

from medical_ratings.maps_supplement import (
    classify_maps_categories,
    deduplicate_maps_by_market,
    keyword_overlap_summary,
)


def observations() -> pd.DataFrame:
    base = {
        "source_api": "maps", "requested_location": "Market_A",
        "retrieved_at_utc": "2026-09-19T00:00:00+00:00", "location_code": 1,
        "language_code": "en", "result_datetime_utc": None, "source_rank": 1,
        "rank_group": 1, "rank_absolute": 1, "address": "1 Main St",
        "address_street": "1 Main St", "city": "City", "latitude": 1.0,
        "longitude": 2.0, "zip": "12345", "address_region": "State",
        "country_code": "US", "phone": None, "domain": None, "url": None,
        "rating_value": 4.5, "votes_count": 10, "rating_1_star": None,
        "rating_2_star": None, "rating_3_star": None, "rating_4_star": None,
        "rating_5_star": None, "item_type": "maps_search",
    }
    return pd.DataFrame([
        {**base, "task_id": "t1", "task_tag": "a", "query": "dentist", "cid": "1", "place_id": "p1", "title": "Clinic One", "category": "Dentist", "additional_categories_json": json.dumps(["Oral surgeon"]), "category_ids_json": "[]"},
        {**base, "task_id": "t2", "task_tag": "b", "query": "dental clinic", "cid": "1", "place_id": "p1", "title": "Clinic One", "category": "Dentist", "additional_categories_json": json.dumps(["Oral surgeon"]), "category_ids_json": "[]"},
        {**base, "task_id": "t2", "task_tag": "b", "query": "dental clinic", "cid": "2", "place_id": "p2", "title": "Clinic Two", "category": "Orthodontist", "additional_categories_json": "null", "category_ids_json": "[]"},
    ])


def rules() -> pd.DataFrame:
    return pd.DataFrame([
        {"category": "Dentist", "legacy_category_group": "keywords_General_Dentist", "group_priority": 1},
        {"category": "Orthodontist", "legacy_category_group": "keywords_Special_Dentist", "group_priority": 2},
        {"category": "Oral surgeon", "legacy_category_group": "keywords_Surgery_Dentist", "group_priority": 3},
    ])


def test_maps_profiles_deduplicate_two_keywords_within_market() -> None:
    candidates = deduplicate_maps_by_market(observations())
    assert len(candidates) == 2
    first = candidates.set_index("cid").loc["1"]
    assert first["observed_queries"] == "dental clinic|dentist"


def test_category_group_uses_returned_categories_with_surgery_precedence() -> None:
    candidates = classify_maps_categories(
        deduplicate_maps_by_market(observations()), rules()
    ).set_index("cid")
    assert candidates.loc["1", "legacy_category_group"] == "keywords_Surgery_Dentist"
    assert (
        candidates.loc["1", "primary_legacy_category_group"]
        == "keywords_General_Dentist"
    )
    assert candidates.loc["1", "has_general_category_evidence"]
    assert candidates.loc["1", "has_surgery_category_evidence"]
    assert candidates.loc["2", "legacy_category_group"] == "keywords_Special_Dentist"


def test_keyword_overlap_counts_marginal_dental_clinic_profiles() -> None:
    overlap = keyword_overlap_summary(deduplicate_maps_by_market(observations()))
    assert overlap.loc[0, "both_keywords_profiles"] == 1
    assert overlap.loc[0, "dental_clinic_only_profiles"] == 1
    assert overlap.loc[0, "dentist_only_profiles"] == 0


def test_paid_items_are_not_treated_as_profiles_or_keyword_duplicates() -> None:
    frame = observations()
    paid = frame.iloc[0].copy()
    paid["item_type"] = "maps_paid_item"
    paid["cid"] = ""
    paid["place_id"] = pd.NA
    paid["title"] = "Sponsored dentist"
    combined = pd.concat([frame, paid.to_frame().T], ignore_index=True)
    candidates = deduplicate_maps_by_market(combined)
    assert len(candidates) == 2
    assert "Sponsored dentist" not in set(candidates["title"])
