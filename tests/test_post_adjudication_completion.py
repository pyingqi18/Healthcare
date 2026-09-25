"""Tests for the combined post-adjudication completion plan."""

import pandas as pd

from medical_ratings.post_adjudication_completion import (
    build_post_adjudication_completion_plan,
)


MARKETS = [f"Market_{index:02d}" for index in range(15)]
KEYWORDS = [
    "family dentist",
    "general dentistry",
    "cosmetic dentist",
    "dental implants",
    "emergency dentist",
]


def source_union() -> pd.DataFrame:
    rows = []
    for index, market in enumerate(MARKETS):
        if index < 10:
            discovered = 9
        elif index < 13:
            discovered = 8
        else:
            discovered = 7
        for unit in range(10):
            rows.append(
                {
                    "market": market,
                    "reference_key": f"competition_unit:{index}:{unit}",
                    "current_reference_included_after_followup": True,
                    "source_union_after_followup": unit < discovered,
                }
            )
    return pd.DataFrame.from_records(rows)


def crosswalk() -> pd.DataFrame:
    rows = []
    for index, market in enumerate(MARKETS):
        for unit in range(10):
            rows.append(
                {
                    "competition_unit_id": f"competition_unit:{index}:{unit}",
                    "clinic_key": f"clinic:{index}:{unit}",
                    "search_location": market,
                    "title": f"Dental Practice {index} {unit}",
                    "address": f"{unit} Main St, Example, ST 00000",
                    "zip": "00000",
                    "latitude": 40.0 + index / 100,
                    "longitude": -75.0,
                    "phone": f"555000{index:02d}{unit:02d}",
                    "domain": f"practice-{index}-{unit}.example",
                }
            )
    return pd.DataFrame.from_records(rows)


def decisions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "decision_id": "identity:one",
                "decision_type": "historical_identity",
                "market": MARKETS[10],
                "subject_key": "one",
                "manual_decision": "unresolved",
                "decision_evidence": "Needs current-status evidence",
            },
            {
                "decision_id": "profile:two",
                "decision_type": "profile_category",
                "market": MARKETS[0],
                "subject_key": "two",
                "manual_decision": "unresolved",
                "decision_evidence": "Category remains ambiguous",
            },
        ]
    )


def regions() -> dict[str, dict[str, int]]:
    return {
        market: {"location_code": 1000000 + index}
        for index, market in enumerate(MARKETS)
    }


def test_completion_plan_separates_frozen_targeted_and_redesign_markets() -> None:
    market_plan, remaining, audit, residual, unresolved, summary = (
        build_post_adjudication_completion_plan(
            source_union(),
            crosswalk(),
            decisions(),
            markets=MARKETS,
            regions=regions(),
            residual_keywords=KEYWORDS,
            primary_market_minimum=0.9,
            reject_market_below=0.8,
            maps_price_per_100_results_usd=0.0006,
        )
    )
    assert market_plan["next_action"].value_counts().to_dict() == {
        "freeze_primary_discovery": 10,
        "targeted_reference_status_audit": 3,
        "discovery_redesign_and_reference_status_audit": 2,
    }
    assert len(remaining) == 22
    assert len(audit) == 12
    assert audit["included_in_main_discovery_pipeline"].eq(False).all()
    assert len(residual) == 75
    assert residual.groupby("market").size().eq(5).all()
    assert set(residual["query"]) == set(KEYWORDS)
    assert len(unresolved) == 2
    assert summary["unique_unresolved_decision_rows"] == 2
    assert summary["legacy_53_combinations_reused"] is False
    assert summary["api_requests_submitted"] == 0
    assert summary["regression_balltree_modified"] is False


def test_completion_plan_rejects_duplicate_keywords() -> None:
    try:
        build_post_adjudication_completion_plan(
            source_union(),
            crosswalk(),
            decisions(),
            markets=MARKETS,
            regions=regions(),
            residual_keywords=["dentist", "dentist"],
            primary_market_minimum=0.9,
            reject_market_below=0.8,
            maps_price_per_100_results_usd=0.0006,
        )
    except ValueError as error:
        assert "unique" in str(error)
    else:
        raise AssertionError("Duplicate residual keywords were accepted")
