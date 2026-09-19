"""Compare LA/NYC discovery sources against one fused historical reference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.business_listings_comparison import (
    build_competition_unit_references,
    classify_competition_unit_reference_geography,
    prepare_pilot_candidates,
)
from medical_ratings.major_metro_source_audit import (
    MAJOR_METRO_MARKETS,
    build_major_metro_three_way_summary,
    compare_major_metro_exact_profiles,
    match_reference_locations_indexed,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit LA/NYC sources against the fused historical reference."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--business-candidates", type=Path, default=None)
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
        "--category-rules",
        type=Path,
        default=Path("config/google_category_rules.csv"),
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "business_candidates": (
                "interim",
                "business_listings_major_metro_zip_filtered_parse/"
                "major_metro_zip_filtered_candidates.csv",
            ),
            "maps_profile_audit": (
                "interim",
                "maps_standard_supplement_audit/standard_rollout/"
                "maps_core_profile_audit.csv",
            ),
            "output_directory": (
                "interim",
                "business_listings_major_metro_source_audit",
            ),
        },
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


def match_each_market(
    reviewed: pd.DataFrame,
    eligible_references: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reuse the established matcher separately within each frozen market."""

    matches: list[pd.DataFrame] = []
    pairs: list[pd.DataFrame] = []
    for market in sorted(MAJOR_METRO_MARKETS):
        market_reviewed = reviewed.loc[
            reviewed["requested_location"].eq(market)
        ].copy()
        market_references = eligible_references.loc[
            eligible_references["search_location"].eq(market)
        ].copy()
        market_matches, market_pairs = match_reference_locations_indexed(
            market_reviewed,
            market_references,
            reference_key_prefix=None,
            target_markets={market},
        )
        matches.append(market_matches)
        pairs.append(market_pairs)
    return (
        pd.concat(matches, ignore_index=True),
        pd.concat(pairs, ignore_index=True),
    )


def main() -> int:
    args = parse_arguments()
    outputs = {
        "business_eligibility": args.output_directory / "major_metro_business_listings_eligibility.csv",
        "maps_eligibility": args.output_directory / "major_metro_maps_standard_eligibility.csv",
        "exact_overlap": args.output_directory / "major_metro_maps_business_exact_profile_overlap.csv",
        "exact_market": args.output_directory / "major_metro_maps_business_exact_profile_overlap_by_market.csv",
        "universe": args.output_directory / "major_metro_fused_historical_reference_universe.csv",
        "business_matches": args.output_directory / "major_metro_business_listings_reference_matches.csv",
        "business_pairs": args.output_directory / "major_metro_business_listings_reference_match_pairs.csv",
        "maps_matches": args.output_directory / "major_metro_maps_standard_reference_matches.csv",
        "maps_pairs": args.output_directory / "major_metro_maps_standard_reference_match_pairs.csv",
        "market": args.output_directory / "major_metro_source_comparison_by_market.csv",
        "summary": args.output_directory / "major_metro_source_comparison_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    business = pd.read_csv(
        args.business_candidates,
        dtype={"cid": "string", "place_id": "string", "zip": "string"},
        low_memory=False,
    )
    maps = pd.read_csv(
        args.maps_profile_audit,
        dtype={"cid": "string", "place_id": "string", "zip": "string"},
        low_memory=False,
    )
    reference = pd.read_csv(
        args.reference_crosswalk,
        dtype={"clinic_key": "string", "zip": "string"},
        low_memory=False,
    )
    regions_payload = yaml.safe_load(args.regions.read_text(encoding="utf-8"))
    regions = regions_payload.get("regions")
    if not isinstance(regions, dict):
        raise KeyError("regions.yaml is missing regions")
    category_rules = pd.read_csv(args.category_rules, low_memory=False)
    business_reviewed = prepare_pilot_candidates(
        business,
        regions,
        category_rules,
        target_markets=MAJOR_METRO_MARKETS,
    )
    maps_major = maps.loc[
        maps["requested_location"].isin(MAJOR_METRO_MARKETS)
    ].copy()
    maps_reviewed = prepare_pilot_candidates(
        maps_major,
        regions,
        category_rules,
        target_markets=MAJOR_METRO_MARKETS,
    )
    unit_references = build_competition_unit_references(
        reference,
        target_markets=MAJOR_METRO_MARKETS,
    )
    universe = classify_competition_unit_reference_geography(
        unit_references,
        regions,
        target_markets=MAJOR_METRO_MARKETS,
    )
    eligible_references = universe.loc[
        universe["reference_geography_status"].eq("eligible_target_zip")
    ].copy()
    business_matches, business_pairs = match_each_market(
        business_reviewed, eligible_references
    )
    maps_matches, maps_pairs = match_each_market(
        maps_reviewed, eligible_references
    )
    exact_overlap, exact_by_market = compare_major_metro_exact_profiles(
        business_reviewed, maps_reviewed
    )
    by_market, summary = build_major_metro_three_way_summary(
        business_reviewed,
        maps_reviewed,
        exact_by_market,
        universe,
        business_matches,
        maps_matches,
    )
    write_csv_atomic(business_reviewed, outputs["business_eligibility"])
    write_csv_atomic(maps_reviewed, outputs["maps_eligibility"])
    write_csv_atomic(exact_overlap, outputs["exact_overlap"])
    write_csv_atomic(exact_by_market, outputs["exact_market"])
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
