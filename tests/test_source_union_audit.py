"""Tests for all-market marginal and union reference recall."""

from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.source_union_audit import (
    build_reference_source_union,
    summarize_reference_source_union,
)


def matches(source: str) -> pd.DataFrame:
    discoveries = {
        "business": [True, True, False, False],
        "maps": [True, False, True, False],
    }[source]
    return pd.DataFrame(
        {
            "market": ["small", "small", "large", "large"],
            "reference_key": ["r1", "r2", "r3", "r4"],
            "discovered": discoveries,
            "best_candidate_key": ["c1", "c2", "c3", None],
        }
    )


def test_union_separates_overlap_increment_and_remaining_gap() -> None:
    union = build_reference_source_union(
        matches("business"), matches("maps"), expected_markets={"small", "large"}
    )
    status = union.set_index("reference_key")["source_discovery_status"]
    assert status["r1"] == "discovered_by_both"
    assert status["r2"] == "business_only"
    assert status["r3"] == "maps_incremental"
    assert status["r4"] == "not_discovered_by_either"


def test_union_rejects_different_reference_universes() -> None:
    maps = matches("maps").iloc[:-1].copy()
    with pytest.raises(ValueError, match="different reference universes"):
        build_reference_source_union(
            matches("business"), maps, expected_markets={"small", "large"}
        )


def test_market_summary_uses_union_not_sum_of_source_recalls() -> None:
    union = build_reference_source_union(
        matches("business"), matches("maps"), expected_markets={"small", "large"}
    )
    by_market, summary = summarize_reference_source_union(
        union,
        expected_markets={"small", "large"},
        primary_market_minimum=0.9,
        reject_market_below=0.8,
    )
    assert summary["business_listings_recall"] == 0.5
    assert summary["maps_standard_recall"] == 0.5
    assert summary["source_union_recall"] == 0.75
    assert summary["maps_incremental_units"] == 1
    decision = by_market.set_index("market")["benchmark_decision"]
    assert decision["small"] == "meets_primary_market_gate"
    assert decision["large"] == "discovery_redesign_required"


def test_threshold_band_requires_targeted_gap_audit() -> None:
    union = pd.DataFrame(
        {
            "market": ["only"] * 10,
            "reference_key": [f"r{i}" for i in range(10)],
            "business_listings_discovered": [True] * 8 + [False] * 2,
            "maps_standard_discovered": [False] * 8 + [True, False],
            "source_union_discovered": [True] * 9 + [False],
            "source_discovery_status": ["business_only"] * 8
            + ["maps_incremental", "not_discovered_by_either"],
        }
    )
    by_market, _ = summarize_reference_source_union(
        union,
        expected_markets={"only"},
        primary_market_minimum=0.95,
        reject_market_below=0.8,
    )
    assert by_market.loc[0, "benchmark_decision"] == "targeted_gap_audit_required"
