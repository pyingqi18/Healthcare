from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.maps_specialist_plan import build_specialist_manifest


MARKETS = [f"market_{index:02d}" for index in range(15)]
KEYWORDS = [
    "orthodontist",
    "pediatric dentist",
    "periodontist",
    "prosthodontist",
    "oral surgeon",
]
REGIONS = {
    market: {"location_code": 1000 + index}
    for index, market in enumerate(MARKETS)
}


def benchmark() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": MARKETS,
            "fused_historical_target_zip_units": [10] * 15,
            "source_union_discovered_units": [9] * 15,
            "source_union_recall": [0.9] * 15,
            "remaining_unmatched_units": [1] * 15,
            "benchmark_decision": ["meets_primary_market_gate"] * 15,
        }
    )


def build(**overrides: object):
    arguments = {
        "markets": MARKETS,
        "keywords": KEYWORDS,
        "regions": REGIONS,
        "price_per_100_results_usd": 0.0006,
    }
    arguments.update(overrides)
    return build_specialist_manifest(benchmark(), **arguments)


def test_builds_same_five_queries_for_all_fifteen_markets() -> None:
    manifest, summary = build()
    assert len(manifest) == 75
    assert manifest.groupby("market").size().eq(5).all()
    assert manifest.groupby("market")["query"].apply(set).eq(set(KEYWORDS)).all()
    assert manifest["task_tag"].is_unique
    assert summary["planned_paid_tasks"] == 75
    assert summary["estimated_standard_cost_usd"] == pytest.approx(0.045)


def test_plan_never_enables_execution_or_api_requests() -> None:
    manifest, summary = build()
    assert manifest["planning_only"].all()
    assert not manifest["execution_enabled"].any()
    assert summary["paid_execution_enabled"] is False
    assert summary["credentials_read"] is False
    assert summary["api_requests_submitted"] == 0


def test_rejects_nonuniform_or_duplicate_keyword_plan() -> None:
    with pytest.raises(ValueError, match="unique"):
        build(keywords=[*KEYWORDS, KEYWORDS[0]])


def test_rejects_benchmark_market_drift() -> None:
    changed = benchmark().iloc[:-1].copy()
    with pytest.raises(ValueError, match="differ"):
        build_specialist_manifest(
            changed,
            markets=MARKETS,
            keywords=KEYWORDS,
            regions=REGIONS,
            price_per_100_results_usd=0.0006,
        )


def test_rejects_missing_region_code() -> None:
    with pytest.raises(KeyError, match="Regions are missing"):
        build(regions={key: value for key, value in REGIONS.items() if key != MARKETS[0]})
