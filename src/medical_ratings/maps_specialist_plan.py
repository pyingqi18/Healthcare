"""Build one uniform, planning-only Maps specialist supplement."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

import pandas as pd


REQUIRED_BENCHMARK_COLUMNS = {
    "market",
    "fused_historical_target_zip_units",
    "source_union_discovered_units",
    "source_union_recall",
    "remaining_unmatched_units",
    "benchmark_decision",
}

REQUIRED_MANIFEST_COLUMNS = {
    "task_tag",
    "plan_type",
    "market",
    "query",
    "location_code",
    "language_code",
    "depth",
    "priority",
    "included_in_main_discovery_pipeline",
}


def validate_specialist_manifest(
    manifest: pd.DataFrame,
    *,
    expected_markets: set[str],
    expected_keywords: set[str],
) -> None:
    """Reject any drift from the frozen 15-market, five-keyword plan."""

    missing = REQUIRED_MANIFEST_COLUMNS - set(manifest.columns)
    if missing:
        raise KeyError(f"Specialist manifest is missing: {sorted(missing)}")
    if len(expected_markets) != 15 or len(expected_keywords) != 5:
        raise ValueError("Execution requires 15 markets and five specialist keywords")
    if len(manifest) != 75:
        raise ValueError("Specialist manifest must contain exactly 75 tasks")
    tags = manifest["task_tag"].astype("string").str.strip()
    if tags.isna().any() or tags.eq("").any() or tags.duplicated().any():
        raise ValueError("Specialist manifest task tags must be unique and nonblank")
    if set(manifest["market"].astype(str)) != expected_markets:
        raise ValueError("Specialist manifest markets differ from the frozen set")
    if set(manifest["query"].astype(str)) != expected_keywords:
        raise ValueError("Specialist manifest keywords differ from the frozen set")
    if set(manifest["plan_type"].astype(str)) != {"market_specialist_discovery"}:
        raise ValueError("Specialist manifest contains a non-specialist plan type")
    included = (
        manifest["included_in_main_discovery_pipeline"]
        .astype("string")
        .str.strip()
        .str.casefold()
    )
    if not included.eq("true").all():
        raise ValueError("Specialist manifest contains tasks outside main discovery")
    if not manifest.groupby("market").size().eq(5).all():
        raise ValueError("Every market must contain exactly five specialist tasks")
    keyword_sets = manifest.groupby("market")["query"].apply(
        lambda values: set(values.astype(str))
    )
    if not keyword_sets.map(lambda values: values == expected_keywords).all():
        raise ValueError("Every market must use the same five specialist keywords")


def build_specialist_manifest(
    benchmark: pd.DataFrame,
    *,
    markets: Sequence[str],
    keywords: Sequence[str],
    regions: Mapping[str, Mapping[str, Any]],
    price_per_100_results_usd: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Create identical specialist queries for every frozen market."""

    missing = REQUIRED_BENCHMARK_COLUMNS - set(benchmark.columns)
    if missing:
        raise KeyError(f"Benchmark table is missing: {sorted(missing)}")
    if benchmark["market"].astype(str).duplicated().any():
        raise ValueError("Benchmark table contains duplicate markets")

    frozen_markets = [str(value).strip() for value in markets]
    clean_keywords = [" ".join(str(value).strip().split()) for value in keywords]
    if len(frozen_markets) != 15 or len(set(frozen_markets)) != 15:
        raise ValueError("Specialist planning requires exactly 15 unique markets")
    if not clean_keywords or any(not value for value in clean_keywords):
        raise ValueError("Specialist keywords cannot be empty")
    if len(set(clean_keywords)) != len(clean_keywords):
        raise ValueError("Specialist keywords must be unique")
    if price_per_100_results_usd <= 0:
        raise ValueError("Maps Standard price must be positive")

    observed_markets = set(benchmark["market"].astype(str))
    if observed_markets != set(frozen_markets):
        raise ValueError("Benchmark markets differ from the frozen 15-market set")
    missing_regions = set(frozen_markets) - set(regions)
    if missing_regions:
        raise KeyError(f"Regions are missing: {sorted(missing_regions)}")

    keyed = benchmark.set_index(benchmark["market"].astype(str), drop=False)
    rows: list[dict[str, Any]] = []
    for market in frozen_markets:
        market_row = keyed.loc[market]
        for keyword in clean_keywords:
            digest = hashlib.sha256(keyword.encode("utf-8")).hexdigest()[:10]
            rows.append(
                {
                    "task_tag": f"maps_specialist:{market}:{digest}",
                    "plan_type": "market_specialist_discovery",
                    "market": market,
                    "query": keyword,
                    "location_code": int(regions[market]["location_code"]),
                    "language_code": "en",
                    "depth": 100,
                    "priority": 1,
                    "estimated_cost_usd": round(
                        float(price_per_100_results_usd), 6
                    ),
                    "benchmark_source_union_recall": float(
                        market_row["source_union_recall"]
                    ),
                    "benchmark_remaining_unmatched_units": int(
                        market_row["remaining_unmatched_units"]
                    ),
                    "benchmark_decision": str(market_row["benchmark_decision"]),
                    "planning_only": True,
                    "execution_enabled": False,
                    "included_in_main_discovery_pipeline": True,
                }
            )
    manifest = pd.DataFrame.from_records(rows)
    if manifest["task_tag"].duplicated().any():
        raise ValueError("Specialist manifest contains duplicate task tags")
    expected_per_market = len(clean_keywords)
    if not manifest.groupby("market").size().eq(expected_per_market).all():
        raise ValueError("Every market must receive the identical keyword count")
    manifest["submission_batch"] = (
        manifest.index.to_series().floordiv(100).add(1).astype(int)
    )

    reference_total = int(
        benchmark["fused_historical_target_zip_units"].sum()
    )
    union_total = int(benchmark["source_union_discovered_units"].sum())
    remaining_total = int(benchmark["remaining_unmatched_units"].sum())
    decision_counts = benchmark["benchmark_decision"].value_counts()
    summary = {
        "analysis_status": "uniform_maps_specialist_supplement_planning_only",
        "planning_only": True,
        "paid_execution_enabled": False,
        "credentials_read": False,
        "api_requests_submitted": 0,
        "market_count": len(frozen_markets),
        "specialist_keywords": clean_keywords,
        "keywords_per_market": len(clean_keywords),
        "planned_paid_tasks": len(manifest),
        "http_post_batches_at_100_tasks": int(
            manifest["submission_batch"].nunique()
        ),
        "estimated_standard_cost_usd": round(
            float(manifest["estimated_cost_usd"].sum()), 6
        ),
        "benchmark_reference_units": reference_total,
        "benchmark_source_union_discovered_units": union_total,
        "benchmark_source_union_recall": union_total / reference_total,
        "benchmark_remaining_unmatched_units": remaining_total,
        "markets_by_benchmark_decision": {
            str(key): int(value) for key, value in decision_counts.items()
        },
        "uniform_scope_reason": (
            "Every market receives the same specialist keywords so discovery "
            "effort does not depend on the observed market recall result."
        ),
        "interpretation_limit": (
            "The manifest expands discovery only. Results still require actual-ZIP, "
            "category, source-identity, and physical-location review."
        ),
    }
    return manifest, summary
