"""Tests for pilot eligibility, reference matching, and recall decisions."""

from __future__ import annotations

import pandas as pd

from medical_ratings.business_listings_comparison import (
    build_competition_unit_references,
    classify_competition_unit_reference_geography,
    match_reference_locations,
    prepare_pilot_candidates,
    summarize_pilot_comparison,
    summarize_rollout_market_comparison,
)


def category_rules() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"category": "Dentist", "category_decision": "include", "reason": "dental"},
            {"category": "Medical clinic", "category_decision": "manual_review", "reason": "review"},
            {"category": "Urgent care center", "category_decision": "exclude", "reason": "medical"},
        ]
    )


def regions() -> dict[str, dict[str, object]]:
    return {
        "Malone_NY_S": {"zip_values": [12953]},
        "Syracuse_NY_M": {"zip_ranges": [[13200, 13299]]},
    }


def candidates() -> pd.DataFrame:
    rows = [
        ("1", "Malone_NY_S", "Malone Dental", "Dentist", "1 Main St", "12953", 44.85, -74.30, "5181112222"),
        ("2", "Syracuse_NY_M", "Syracuse Dental", "Dentist", "2 Main St", "132142121", 43.04, -76.10, "3151112222"),
        ("3", "Syracuse_NY_M", "Mixed Health", "Medical clinic", "3 Main St", "13202", 43.05, -76.15, "3152223333"),
        ("4", "Syracuse_NY_M", "Outside Dental", "Dentist", "4 Main St", "13066", 43.10, -76.00, "3153334444"),
        ("5", "Syracuse_NY_M", "Missing ZIP", "Dentist", "5 Main St", None, 43.06, -76.16, "3154445555"),
        ("6", "Syracuse_NY_M", "Canadian Dental", "Dentist", "6 Main St", "L2G 6B9", 43.07, -76.17, "9054445555"),
    ]
    return pd.DataFrame(
        [
            {
                "profile_key": f"google:cid:{cid}",
                "cid": cid,
                "place_id": f"place-{cid}",
                "requested_location": market,
                "title": title,
                "category": category,
                "address": address,
                "zip": zip_value,
                "latitude": latitude,
                "longitude": longitude,
                "phone": phone,
                "domain": None,
            }
            for cid, market, title, category, address, zip_value, latitude, longitude, phone in rows
        ]
    )


def test_prepare_candidates_normalizes_zip9_and_keeps_all_statuses() -> None:
    reviewed = prepare_pilot_candidates(candidates(), regions(), category_rules())
    status = reviewed.set_index("cid")
    assert status.loc["2", "normalized_zip"] == "13214"
    assert status.loc["2", "eligibility_review_status"] == "include_dental_provider"
    assert status.loc["3", "eligibility_review_status"] == "manual_category_review"
    assert status.loc["4", "eligibility_review_status"] == "exclude_outside_target_zip"
    assert status.loc["5", "eligibility_review_status"] == "needs_geography"
    assert status.loc["5", "postal_code_status"] == "missing"
    assert status.loc["6", "postal_code_status"] == "non_us_postal"
    assert status.loc["6", "market_assignment_status"] == "outside_target_zip"
    assert status.loc["6", "eligibility_review_status"] == "exclude_outside_target_zip"


def test_reference_matching_requires_identity_evidence_for_ten_meter_rule() -> None:
    reviewed = prepare_pilot_candidates(candidates(), regions(), category_rules())
    reference = pd.DataFrame(
        [
            {
                "clinic_key": "physical_location_final:malone",
                "search_location": "Malone_NY_S",
                "title": "Old Malone",
                "address": "1 Main St",
                "zip": "12953",
                "latitude": 44.85,
                "longitude": -74.30,
                "phone": "518-111-2222",
                "domain": None,
            },
            {
                "clinic_key": "physical_location_final:manual",
                "search_location": "Syracuse_NY_M",
                "title": "Mixed Health",
                "address": "3 Main St",
                "zip": "13202",
                "latitude": 43.05,
                "longitude": -76.15,
                "phone": "315-222-3333",
                "domain": None,
            },
            {
                "clinic_key": "physical_location_final:missing",
                "search_location": "Syracuse_NY_M",
                "title": "Not Found",
                "address": "99 Missing St",
                "zip": "13203",
                "latitude": 43.20,
                "longitude": -76.30,
                "phone": None,
                "domain": None,
            },
        ]
    )
    matches, pairs = match_reference_locations(reviewed, reference)
    indexed = matches.set_index("reference_key")
    assert bool(indexed.loc["physical_location_final:malone", "discovered"])
    assert bool(indexed.loc["physical_location_final:malone", "discovered_with_provisional_include"])
    assert bool(indexed.loc["physical_location_final:manual", "discovered"])
    assert not bool(indexed.loc["physical_location_final:manual", "discovered_with_provisional_include"])
    assert not bool(indexed.loc["physical_location_final:missing", "discovered"])
    assert len(pairs) == 2


def test_coordinate_only_pair_is_reviewed_but_not_counted_as_discovered() -> None:
    reviewed = prepare_pilot_candidates(candidates(), regions(), category_rules())
    reference = pd.DataFrame(
        [
            {
                "clinic_key": "physical_location_final:coordinate-only",
                "search_location": "Syracuse_NY_M",
                "title": "Completely Different Practice",
                "address": "99 Other St",
                "zip": "13214",
                "latitude": 43.04,
                "longitude": -76.10,
                "phone": None,
                "domain": None,
            }
        ]
    )
    matches, pairs = match_reference_locations(reviewed, reference)
    assert not bool(matches.loc[0, "discovered"])
    assert matches.loc[0, "coordinate_only_review_candidate_count"] == 1
    assert pairs.loc[0, "matching_evidence"] == "coordinate_only_within_10m_review"
    assert not bool(pairs.loc[0, "fixed_rule_match"])


def test_summary_counts_zero_item_paid_request_and_recall_gate() -> None:
    reviewed = prepare_pilot_candidates(candidates(), regions(), category_rules())
    matches = pd.DataFrame(
        [
            {"reference_key": f"m-{index}", "market": "Malone_NY_S", "discovered": True, "discovered_with_provisional_include": True}
            for index in range(8)
        ]
        + [
            {"reference_key": f"s-{index}", "market": "Syracuse_NY_M", "discovered": index < 96, "discovered_with_provisional_include": index < 95}
            for index in range(101)
        ]
    )
    log = pd.DataFrame(
        [
            {"task_tag": f"task-{index}", "request_status": "completed", "api_cost_usd": cost, "item_count": count}
            for index, (cost, count) in enumerate(
                [(0.01884, 19), (0.01236, 0), (0.18192, 472), (0.02748, 43)]
            )
        ]
    )
    gate = {
        "approve_primary_overall_minimum": 0.95,
        "approve_primary_each_market_minimum": 0.90,
        "supplement_overall_minimum": 0.90,
        "reject_each_market_below": 0.80,
    }
    market, summary = summarize_pilot_comparison(reviewed, matches, gate, log)
    assert summary["actual_api_cost_usd"] == 0.2406
    assert summary["raw_items_reported"] == 534
    assert summary["decision"] == "approve_as_primary"
    assert summary["unmatched_reference_locations"] == 5
    assert market.set_index("market").loc["Syracuse_NY_M", "recall"] == 96 / 101


def test_prepare_candidates_supports_one_frozen_rollout_market() -> None:
    atlanta_regions = {
        "Atlanta_GA_L": {"zip_ranges": [[30300, 30399], [31100, 31199]]}
    }
    atlanta = candidates().iloc[[0]].copy()
    atlanta["requested_location"] = "Atlanta_GA_L"
    atlanta["zip"] = "30303"
    reviewed = prepare_pilot_candidates(
        atlanta,
        atlanta_regions,
        category_rules(),
        target_markets={"Atlanta_GA_L"},
    )
    assert reviewed.loc[reviewed.index[0], "mapped_location"] == "Atlanta_GA_L"
    assert (
        reviewed.loc[reviewed.index[0], "eligibility_review_status"]
        == "include_dental_provider"
    )


def test_competition_unit_reference_collapses_shared_profiles() -> None:
    reference = pd.DataFrame(
        [
            {
                "clinic_key": f"profile-{index}",
                "competition_unit_id": "address_unit:atlanta",
                "search_location": "Atlanta_GA_L",
                "title": title,
                "address": "1 Peachtree St",
                "zip": "30303",
                "latitude": latitude,
                "longitude": -84.388,
                "phone": phone,
                "domain": None,
            }
            for index, title, latitude, phone in [
                (1, "Atlanta Dental", 33.7490, "4041112222"),
                (2, "Atlanta Dental Group", 33.7491, None),
            ]
        ]
    )
    units = build_competition_unit_references(
        reference,
        target_markets={"Atlanta_GA_L"},
    )
    assert len(units) == 1
    assert units.loc[0, "clinic_key"] == "address_unit:atlanta"
    assert units.loc[0, "reference_source_profile_count"] == 2


def test_competition_unit_reference_geography_separates_recall_denominator() -> None:
    references = pd.DataFrame(
        [
            {"clinic_key": "inside", "search_location": "Atlanta_GA_L", "zip": "30303"},
            {"clinic_key": "outside", "search_location": "Atlanta_GA_L", "zip": "30080"},
            {"clinic_key": "missing", "search_location": "Atlanta_GA_L", "zip": None},
        ]
    )
    classified = classify_competition_unit_reference_geography(
        references,
        {"Atlanta_GA_L": {"zip_ranges": [[30300, 30399], [31100, 31199]]}},
        target_markets={"Atlanta_GA_L"},
    ).set_index("clinic_key")
    assert classified.loc["inside", "reference_geography_status"] == "eligible_target_zip"
    assert classified.loc["outside", "reference_geography_status"] == "outside_target_zip"
    assert classified.loc["missing", "reference_geography_status"] == "missing_zip"


def test_rollout_summary_uses_all_completed_market_pages() -> None:
    atlanta_regions = {
        "Atlanta_GA_L": {"zip_ranges": [[30300, 30399], [31100, 31199]]}
    }
    atlanta = candidates().iloc[[0]].copy()
    atlanta["requested_location"] = "Atlanta_GA_L"
    atlanta["zip"] = "30303"
    reviewed = prepare_pilot_candidates(
        atlanta,
        atlanta_regions,
        category_rules(),
        target_markets={"Atlanta_GA_L"},
    )
    matches = pd.DataFrame(
        [
            {
                "reference_key": "physical_location_final:atlanta",
                "market": "Atlanta_GA_L",
                "discovered": True,
                "discovered_with_provisional_include": True,
            }
        ]
    )
    log = pd.DataFrame(
        [
            {
                "task_tag": f"atlanta-p{page}",
                "market": "Atlanta_GA_L",
                "request_status": "completed",
                "api_cost_usd": cost,
                "item_count": count,
            }
            for page, cost, count in [
                (1, 0.372, 1000),
                (2, 0.372, 1000),
                (3, 0.372, 1000),
                (4, 0.2424, 640),
                (5, 0.18552, 482),
            ]
        ]
    )
    gate = {
        "approve_primary_overall_minimum": 0.95,
        "approve_primary_each_market_minimum": 0.90,
        "supplement_overall_minimum": 0.90,
        "reject_each_market_below": 0.80,
    }
    _, summary = summarize_rollout_market_comparison(
        reviewed,
        matches,
        gate,
        log,
        market="Atlanta_GA_L",
        reference_universe=pd.DataFrame(
            [
                {
                    "search_location": "Atlanta_GA_L",
                    "reference_geography_status": "eligible_target_zip",
                },
                {
                    "search_location": "Atlanta_GA_L",
                    "reference_geography_status": "outside_target_zip",
                },
                {
                    "search_location": "Atlanta_GA_L",
                    "reference_geography_status": "missing_zip",
                },
            ]
        ),
    )
    assert summary["completed_paid_requests"] == 5
    assert summary["raw_items_reported"] == 4122
    assert summary["actual_api_cost_usd"] == 1.54392
    assert summary["decision"] == "approve_as_primary"
    assert summary["legacy_reference_universe"] == {
        "all_competition_units_labeled_as_market": 3,
        "eligible_target_zip_units": 1,
        "outside_target_zip_units": 1,
        "missing_zip_units": 1,
        "recall_denominator": "eligible_target_zip_units_only",
    }
