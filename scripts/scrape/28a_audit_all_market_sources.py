"""Recompute one uniform three-source comparison for all 15 markets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.all_market_source_audit import (
    build_all_market_summary,
    combine_business_listings_sources,
    compare_exact_profiles,
    match_each_market,
)
from medical_ratings.business_listings_comparison import (
    build_competition_unit_references,
    classify_competition_unit_reference_geography,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit all 15 markets against one fused historical reference."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--pilot-business", type=Path, default=None)
    parser.add_argument("--atlanta-business", type=Path, default=None)
    parser.add_argument("--standard-business", type=Path, default=None)
    parser.add_argument("--major-metro-business", type=Path, default=None)
    parser.add_argument("--maps-profile-audit", type=Path, default=None)
    parser.add_argument(
        "--reference-crosswalk",
        type=Path,
        default=Path(
            "outputs/diagnostics/corrected_v1/competition_units/"
            "competition_unit_crosswalk.csv"
        ),
    )
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
            "pilot_business": (
                "interim",
                "business_listings_pilot_manual_audit/"
                "business_listings_adjudicated_candidates.csv",
            ),
            "atlanta_business": (
                "interim",
                "business_listings_rollout_market_comparison/"
                "business_listings_rollout_eligibility.csv",
            ),
            "standard_business": (
                "interim",
                "business_listings_rollout_stage_comparison/standard_rollout/"
                "business_listings_rollout_stage_eligibility.csv",
            ),
            "major_metro_business": (
                "interim",
                "business_listings_major_metro_source_audit/"
                "major_metro_business_listings_eligibility.csv",
            ),
            "maps_profile_audit": (
                "interim",
                "maps_standard_supplement_audit/standard_rollout/"
                "maps_core_profile_audit.csv",
            ),
            "output_directory": (
                "interim",
                "all_market_source_audit",
            ),
        },
    )


def read_yaml(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return payload


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype={"cid": "string", "place_id": "string", "zip": "string"},
        low_memory=False,
    )


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def write_json_atomic(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def frozen_market_sources(plan: dict[str, object]) -> tuple[list[str], dict[str, set[str]]]:
    profiles = plan.get("profiles")
    rollout = plan.get("business_listings_rollout")
    if not isinstance(profiles, dict) or not isinstance(rollout, dict):
        raise KeyError("scrape_plans.yaml is missing profiles or rollout settings")
    profile = profiles.get("existing_15_markets_planning_v1")
    if not isinstance(profile, dict) or not isinstance(profile.get("markets"), list):
        raise KeyError("scrape_plans.yaml is missing the frozen 15-market profile")
    all_markets = [str(value) for value in profile["markets"]]
    if len(all_markets) != 15 or len(set(all_markets)) != 15:
        raise ValueError("Frozen planning profile must contain 15 unique markets")
    pilot = {str(value) for value in rollout.get("validated_pilot_markets", [])}
    major = {str(value) for value in rollout.get("major_metro_review_markets", [])}
    atlanta_value = str(rollout.get("large_market_validation_market", "")).strip()
    if len(pilot) != 2 or len(major) != 2 or not atlanta_value:
        raise ValueError("Frozen Business Listings market stages are incomplete")
    atlanta = {atlanta_value}
    standard = set(all_markets) - pilot - major - atlanta
    if len(standard) != 10:
        raise ValueError("The standard rollout stage must contain exactly 10 markets")
    return all_markets, {
        "pilot_adjudicated": pilot,
        "atlanta_validation": atlanta,
        "standard_rollout": standard,
        "major_metro_zip_filtered": major,
    }


def main() -> int:
    args = parse_arguments()
    outputs = {
        "business": args.output_directory / "all_market_business_listings_eligibility.csv",
        "exact": args.output_directory / "all_market_maps_business_exact_profile_overlap.csv",
        "exact_market": args.output_directory / "all_market_maps_business_exact_profile_overlap_by_market.csv",
        "universe": args.output_directory / "all_market_fused_historical_reference_universe.csv",
        "business_matches": args.output_directory / "all_market_business_listings_reference_matches.csv",
        "business_pairs": args.output_directory / "all_market_business_listings_reference_match_pairs.csv",
        "maps_matches": args.output_directory / "all_market_maps_standard_reference_matches.csv",
        "maps_pairs": args.output_directory / "all_market_maps_standard_reference_match_pairs.csv",
        "market": args.output_directory / "all_market_source_comparison_by_market.csv",
        "summary": args.output_directory / "all_market_source_comparison_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    plan = read_yaml(args.plan_config)
    all_markets, expected_by_source = frozen_market_sources(plan)
    expected = set(all_markets)
    business = combine_business_listings_sources(
        {
            "pilot_adjudicated": read_csv(args.pilot_business),
            "atlanta_validation": read_csv(args.atlanta_business),
            "standard_rollout": read_csv(args.standard_business),
            "major_metro_zip_filtered": read_csv(args.major_metro_business),
        },
        expected_by_source,
    )
    maps = read_csv(args.maps_profile_audit)
    reference = read_csv(args.reference_crosswalk)
    maps_markets = set(maps["requested_location"].dropna().astype(str))
    if maps_markets != expected:
        raise ValueError("Maps profile audit does not contain the frozen 15 markets")
    regions_payload = read_yaml(args.regions)
    regions = regions_payload.get("regions")
    if not isinstance(regions, dict):
        raise KeyError("regions.yaml is missing regions")

    unit_references = build_competition_unit_references(
        reference, target_markets=expected
    )
    universe = classify_competition_unit_reference_geography(
        unit_references,
        regions,
        target_markets=expected,
    )
    eligible = universe.loc[
        universe["reference_geography_status"].eq("eligible_target_zip")
    ].copy()
    business_matches, business_pairs = match_each_market(
        business, eligible, expected_markets=expected
    )
    maps_matches, maps_pairs = match_each_market(
        maps, eligible, expected_markets=expected
    )
    exact, exact_market = compare_exact_profiles(
        business, maps, expected_markets=expected
    )
    by_market, summary = build_all_market_summary(
        business,
        maps,
        exact_market,
        universe,
        business_matches,
        maps_matches,
        expected_markets=expected,
    )
    write_csv_atomic(business, outputs["business"])
    write_csv_atomic(exact, outputs["exact"])
    write_csv_atomic(exact_market, outputs["exact_market"])
    write_csv_atomic(universe, outputs["universe"])
    write_csv_atomic(business_matches, outputs["business_matches"])
    write_csv_atomic(business_pairs, outputs["business_pairs"])
    write_csv_atomic(maps_matches, outputs["maps_matches"])
    write_csv_atomic(maps_pairs, outputs["maps_pairs"])
    write_csv_atomic(by_market, outputs["market"])
    write_json_atomic(summary, outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(by_market.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
