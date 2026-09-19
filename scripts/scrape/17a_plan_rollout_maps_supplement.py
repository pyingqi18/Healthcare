"""Plan Maps supplements and legacy-reference verification without API calls."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plan Google Maps core supplements and unmatched legacy-reference "
            "verification without submitting paid tasks."
        )
    )
    add_run_context_arguments(parser)
    parser.add_argument("--stage", default="standard_rollout")
    parser.add_argument("--market-comparison", type=Path, default=None)
    parser.add_argument("--reference-matches", type=Path, default=None)
    parser.add_argument("--eligibility", type=Path, default=None)
    parser.add_argument("--regions", type=Path, default=Path("config/regions.yaml"))
    parser.add_argument(
        "--plan-config", type=Path, default=Path("config/scrape_plans.yaml")
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "market_comparison": (
                "interim",
                "business_listings_rollout_stage_comparison/standard_rollout/"
                "business_listings_rollout_stage_market_comparison.csv",
            ),
            "reference_matches": (
                "interim",
                "business_listings_rollout_stage_comparison/standard_rollout/"
                "business_listings_rollout_stage_reference_matches.csv",
            ),
            "eligibility": (
                "interim",
                "business_listings_rollout_stage_comparison/standard_rollout/"
                "business_listings_rollout_stage_eligibility.csv",
            ),
            "output_directory": (
                "interim",
                "business_listings_rollout_supplement_plan",
            ),
        },
    )


def read_yaml(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return payload


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def write_json_atomic(payload: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).strip().split())


def _json_text(value: Any) -> str:
    """Convert YAML date-like scalar values to stable JSON text."""

    return "" if value is None else str(value)


def audit_recall_gaps(reference_matches: pd.DataFrame) -> pd.DataFrame:
    """Add transparent review flags to unmatched corrected legacy references."""

    required = {
        "reference_key",
        "market",
        "reference_title",
        "reference_address",
        "discovered",
        "best_candidate_key",
        "best_distance_meters",
        "best_title_similarity",
    }
    missing = required - set(reference_matches.columns)
    if missing:
        raise KeyError(f"Reference matches are missing: {sorted(missing)}")
    if reference_matches["reference_key"].astype(str).duplicated().any():
        raise ValueError("Reference matches contain duplicate reference keys")
    discovered = (
        reference_matches["discovered"]
        .astype(str)
        .str.strip()
        .str.lower()
        .eq("true")
    )
    gaps = reference_matches.loc[~discovered].copy()
    if gaps.empty:
        return gaps
    distance = pd.to_numeric(gaps["best_distance_meters"], errors="coerce")
    similarity = pd.to_numeric(gaps["best_title_similarity"], errors="coerce")
    gaps["best_candidate_available"] = gaps["best_candidate_key"].notna()
    gaps["best_candidate_within_50m"] = distance.le(50).fillna(False)
    gaps["best_candidate_within_100m"] = distance.le(100).fillna(False)
    gaps["best_candidate_within_500m"] = distance.le(500).fillna(False)
    gaps["best_title_similarity_at_least_0p8"] = similarity.ge(0.8).fillna(False)
    gaps["gap_review_tier"] = "targeted_reference_search"
    gaps.loc[
        ~gaps["best_candidate_available"], "gap_review_tier"
    ] = "no_eligible_candidate_pool"
    gaps.loc[
        gaps["best_candidate_within_100m"]
        & gaps["best_title_similarity_at_least_0p8"],
        "gap_review_tier",
    ] = "close_identity_review"
    gaps.loc[
        ~gaps["best_candidate_within_100m"]
        & gaps["best_candidate_within_500m"]
        & similarity.ge(0.9).fillna(False),
        "gap_review_tier",
    ] = "possible_relocation_or_coordinate_shift"
    gaps["automatic_match_performed"] = False
    return gaps.sort_values(
        ["market", "gap_review_tier", "reference_key"], ignore_index=True
    )


def audit_missing_zip_candidates(eligibility: pd.DataFrame) -> pd.DataFrame:
    """Keep only genuinely missing postal codes for geography review."""

    required = {
        "profile_key",
        "requested_location",
        "zip",
        "normalized_zip",
        "market_assignment_status",
    }
    missing = required - set(eligibility.columns)
    if missing:
        raise KeyError(f"Eligibility table is missing: {sorted(missing)}")
    selected = eligibility.loc[
        eligibility["market_assignment_status"].eq("maps_missing_zip")
    ].copy()
    raw_missing = selected["zip"].isna() | selected["zip"].astype("string").str.strip().eq("")
    if not raw_missing.all():
        raise ValueError(
            "maps_missing_zip must contain only genuinely absent postal codes; "
            "rerun candidate eligibility with postal_code_status"
        )
    selected["missing_zip_reason"] = "source_zip_missing"
    return selected.sort_values(
        ["requested_location", "missing_zip_reason", "profile_key"],
        ignore_index=True,
    )


def build_maps_supplement_plan(
    discovery_markets: list[str],
    recall_gaps: pd.DataFrame,
    regions: Mapping[str, Mapping[str, Any]],
    *,
    core_keywords: list[str],
    price_per_serp_usd: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build a uniform discovery plan and a separate nonpipeline legacy audit."""

    if not core_keywords or any(not str(value).strip() for value in core_keywords):
        raise ValueError("Core supplement keywords cannot be empty")
    if price_per_serp_usd <= 0:
        raise ValueError("SERP price must be positive")
    markets = sorted({str(value).strip() for value in discovery_markets})
    if not markets or any(not value for value in markets):
        raise ValueError("Discovery markets cannot be empty")
    missing_regions = set(markets) - set(regions)
    if missing_regions:
        raise KeyError(f"Discovery markets are missing from regions: {sorted(missing_regions)}")
    core_rows: list[dict[str, Any]] = []
    for market in markets:
        region = _mapping(regions.get(market), f"region {market}")
        location_code = int(region["location_code"])
        for keyword in core_keywords:
            clean_keyword = str(keyword).strip()
            digest = hashlib.sha256(clean_keyword.encode("utf-8")).hexdigest()[:10]
            core_rows.append(
                {
                    "task_tag": f"maps_core:{market}:{digest}",
                    "plan_type": "market_core_discovery",
                    "market": market,
                    "reference_keys": None,
                    "reference_location_count": 0,
                    "query": clean_keyword,
                    "location_code": location_code,
                    "language_code": "en",
                    "depth": 100,
                    "priority": 1,
                    "estimated_cost_usd": round(float(price_per_serp_usd), 6),
                    "planning_only": True,
                    "execution_enabled": False,
                    "included_in_main_discovery_pipeline": True,
                }
            )
    core = pd.DataFrame.from_records(core_rows)

    verification_source = recall_gaps.copy()
    verification_source["query"] = verification_source.apply(
        lambda row: _clean_text(
            " ".join(
                part
                for part in [
                    _clean_text(row["reference_title"]),
                    _clean_text(row["reference_address"]),
                ]
                if part
            )
        )[:700],
        axis=1,
    )
    if verification_source["query"].eq("").any():
        raise ValueError("An unmatched reference lacks both title and address")
    verification_rows: list[dict[str, Any]] = []
    grouped = verification_source.groupby(["market", "query"], sort=True)
    for (market, query), group in grouped:
        region = _mapping(regions.get(str(market)), f"region {market}")
        reference_keys = sorted(group["reference_key"].astype(str))
        digest = hashlib.sha256(
            f"{market}|{query}".encode("utf-8")
        ).hexdigest()[:16]
        verification_rows.append(
            {
                "task_tag": f"maps_reference:{market}:{digest}",
                "plan_type": "unmatched_reference_verification",
                "market": str(market),
                "reference_keys": "|".join(reference_keys),
                "reference_location_count": len(reference_keys),
                "query": str(query),
                "location_code": int(region["location_code"]),
                "language_code": "en",
                "depth": 100,
                "priority": 1,
                "estimated_cost_usd": round(float(price_per_serp_usd), 6),
                "planning_only": True,
                "execution_enabled": False,
                "included_in_main_discovery_pipeline": False,
            }
        )
    verification = pd.DataFrame.from_records(verification_rows)
    if core.empty or core["task_tag"].duplicated().any():
        raise ValueError("Main discovery supplement requires unique nonempty task tags")
    if not verification.empty and verification["task_tag"].duplicated().any():
        raise ValueError("Legacy audit plan requires unique task tags")
    core["submission_batch"] = (
        core.index.to_series().floordiv(100).add(1).astype(int)
    )
    return (
        core.reset_index(drop=True),
        verification.reset_index(drop=True),
        core.reset_index(drop=True).copy(),
    )


def main() -> int:
    args = parse_arguments()
    stage = str(args.stage).strip()
    stage_directory = args.output_directory / stage
    summary_path = stage_directory / "business_listings_rollout_supplement_plan_summary.json"
    if summary_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output already exists: {summary_path}. Use --overwrite to replace it."
        )

    market_comparison = pd.read_csv(args.market_comparison, low_memory=False)
    reference_matches = pd.read_csv(args.reference_matches, low_memory=False)
    eligibility = pd.read_csv(
        args.eligibility,
        dtype={"zip": "string", "normalized_zip": "string"},
        low_memory=False,
    )
    gaps = audit_recall_gaps(reference_matches)
    missing_zip = audit_missing_zip_candidates(eligibility)

    regions_payload = read_yaml(args.regions)
    regions = _mapping(regions_payload.get("regions"), "regions")
    plan = read_yaml(args.plan_config)
    pricing = _mapping(plan.get("pricing"), "pricing")
    profiles = _mapping(plan.get("profiles"), "profiles")
    profile = _mapping(
        profiles.get("existing_15_markets_planning_v1"),
        "existing_15_markets_planning_v1",
    )
    phases = profile.get("phases")
    if not isinstance(phases, list):
        raise TypeError("Planning profile phases must be a list")
    core_phase = next(
        (
            phase
            for phase in phases
            if isinstance(phase, Mapping)
            and phase.get("phase_id") == "maps_core_keyword_supplement"
        ),
        None,
    )
    if not isinstance(core_phase, Mapping):
        raise KeyError("Planning profile is missing maps_core_keyword_supplement")
    core_keywords = [str(value) for value in core_phase.get("keywords", [])]
    profile_markets = profile.get("markets")
    if not isinstance(profile_markets, list):
        raise TypeError("Planning profile markets must be a list")
    discovery_markets = [str(value).strip() for value in profile_markets]
    if len(discovery_markets) != 15 or len(set(discovery_markets)) != 15:
        raise ValueError("Planning profile must contain exactly 15 unique markets")
    pilot = _mapping(plan.get("business_listings_pilot"), "business_listings_pilot")
    _mapping(pilot.get("recall_gate"), "recall_gate")
    price = float(pricing["google_maps_standard_per_100_results"])
    core, verification, combined = build_maps_supplement_plan(
        discovery_markets,
        gaps,
        regions,
        core_keywords=core_keywords,
        price_per_serp_usd=price,
    )

    write_csv_atomic(
        gaps,
        stage_directory / "business_listings_rollout_recall_gap_audit.csv",
    )
    write_csv_atomic(
        missing_zip,
        stage_directory / "business_listings_rollout_missing_zip_candidates.csv",
    )
    write_csv_atomic(
        core,
        stage_directory / "business_listings_rollout_maps_core_plan.csv",
    )
    write_csv_atomic(
        verification,
        stage_directory / "business_listings_rollout_legacy_reference_audit_plan.csv",
    )
    write_csv_atomic(
        combined,
        stage_directory / "business_listings_rollout_supplement_manifest.csv",
    )
    gap_counts = gaps["gap_review_tier"].value_counts()
    missing_counts = missing_zip["missing_zip_reason"].value_counts()
    summary = {
        "analysis_status": "rollout_maps_supplement_planning_only",
        "stage": stage,
        "pricing_verified_on": _json_text(pricing.get("verified_on")),
        "standard_maps_price_per_100_results_usd": price,
        "uniform_core_supplement_markets": sorted(core["market"].unique()),
        "uniform_core_supplement_market_count": int(core["market"].nunique()),
        "reference_audit_scope_markets": sorted(
            market_comparison["market"].astype(str).unique()
        ),
        "main_discovery_market_keyword_requests": len(core),
        "unmatched_reference_locations": len(gaps),
        "legacy_audit_queries_excluded_from_main_pipeline": len(verification),
        "legacy_locations_covered_by_separate_audit": int(
            verification["reference_location_count"].sum()
        ),
        "recall_gap_review_tiers": {
            str(key): int(value) for key, value in gap_counts.items()
        },
        "missing_zip_candidates": len(missing_zip),
        "missing_zip_reasons": {
            str(key): int(value) for key, value in missing_counts.items()
        },
        "main_pipeline_planned_requests": len(combined),
        "main_pipeline_submission_batches_at_100_tasks": int(
            combined["submission_batch"].nunique()
        ),
        "estimated_main_pipeline_standard_cost_usd": round(
            float(combined["estimated_cost_usd"].sum()), 6
        ),
        "planning_only": True,
        "paid_execution_enabled": False,
        "credentials_read": False,
        "api_requests_submitted": 0,
        "next_decision": (
            "Review the uniform discovery manifest separately from the legacy "
            "audit plan before implementing any paid Standard Queue submission."
        ),
    }
    write_json_atomic(summary, summary_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
