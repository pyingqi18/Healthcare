"""Audit specialist Maps ZIPs, identities, and reference-union recall."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from medical_ratings.all_market_source_audit import match_each_market
from medical_ratings.business_listings_comparison import (
    build_competition_unit_references,
    classify_competition_unit_reference_geography,
)
from medical_ratings.maps_specialist_source_audit import (
    build_existing_profile_index,
    compare_specialist_profiles,
    extend_adjudicated_source_union,
)
from medical_ratings.maps_supplement_audit import audit_maps_candidates
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit specialist Maps results without API calls or location merges."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--specialist-candidates", type=Path, default=None)
    parser.add_argument("--business-profiles", type=Path, default=None)
    parser.add_argument("--core-maps-profiles", type=Path, default=None)
    parser.add_argument("--adjudicated-union", type=Path, default=None)
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
        "--category-rules", type=Path, default=Path("config/google_category_rules.csv")
    )
    parser.add_argument(
        "--plan-config", type=Path, default=Path("config/scrape_plans.yaml")
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "specialist_candidates": (
                "interim",
                "maps_specialist_supplement_parse/maps_specialist_candidates.csv",
            ),
            "business_profiles": (
                "interim",
                "all_market_source_audit/all_market_business_listings_eligibility.csv",
            ),
            "core_maps_profiles": (
                "interim",
                "maps_standard_supplement_audit/standard_rollout/"
                "maps_core_profile_audit.csv",
            ),
            "adjudicated_union": (
                "interim",
                "adjudicated_source_union/adjudicated_reference_source_union.csv",
            ),
            "output_directory": (
                "interim",
                "maps_specialist_source_union_audit",
            ),
        },
    )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype={"cid": "string", "place_id": "string", "zip": "string"},
        low_memory=False,
    )


def main() -> int:
    args = parse_arguments()
    outputs = {
        "profiles": args.output_directory / "maps_specialist_profile_audit.csv",
        "exact": args.output_directory / "maps_specialist_exact_source_overlap.csv",
        "exact_market": args.output_directory
        / "maps_specialist_exact_source_overlap_by_market.csv",
        "matches": args.output_directory / "maps_specialist_reference_matches.csv",
        "pairs": args.output_directory / "maps_specialist_reference_match_pairs.csv",
        "union": args.output_directory / "source_union_after_specialist.csv",
        "market": args.output_directory
        / "source_union_after_specialist_by_market.csv",
        "remaining": args.output_directory
        / "remaining_unmatched_after_specialist.csv",
        "summary": args.output_directory
        / "maps_specialist_source_union_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    plan = yaml.safe_load(args.plan_config.read_text(encoding="utf-8"))
    profile = plan["profiles"]["existing_15_markets_planning_v1"]
    expected = {str(value) for value in profile["markets"]}
    if len(expected) != 15:
        raise ValueError("Frozen planning profile must contain 15 unique markets")
    gate = plan["business_listings_pilot"]["recall_gate"]
    regions_payload = yaml.safe_load(args.regions.read_text(encoding="utf-8"))
    regions = _mapping(regions_payload.get("regions"), "regions")

    specialist_reviewed = audit_maps_candidates(
        _read_csv(args.specialist_candidates),
        regions,
        pd.read_csv(args.category_rules, low_memory=False),
    )
    existing_profile_index = build_existing_profile_index(
        _read_csv(args.business_profiles),
        _read_csv(args.core_maps_profiles),
        expected_markets=expected,
    )
    exact, exact_market = compare_specialist_profiles(
        specialist_reviewed,
        existing_profile_index,
        expected_markets=expected,
    )

    references = build_competition_unit_references(
        _read_csv(args.reference_crosswalk), target_markets=expected
    )
    universe = classify_competition_unit_reference_geography(
        references, regions, target_markets=expected
    )
    eligible_references = universe.loc[
        universe["reference_geography_status"].eq("eligible_target_zip")
    ].copy()
    specialist_matches, specialist_pairs = match_each_market(
        specialist_reviewed,
        eligible_references,
        expected_markets=expected,
    )
    combined, by_market, summary = extend_adjudicated_source_union(
        pd.read_csv(args.adjudicated_union, low_memory=False),
        specialist_matches,
        exact_market,
        expected_markets=expected,
        primary_market_minimum=float(
            gate["approve_primary_each_market_minimum"]
        ),
        reject_market_below=float(gate["reject_each_market_below"]),
    )
    status_counts = specialist_reviewed["market_assignment_status"].value_counts()
    category_counts = specialist_reviewed["eligibility_review_status"].value_counts()
    summary.update(
        {
            "input_specialist_profiles": len(specialist_reviewed),
            "specialist_market_assignment_status_counts": {
                str(key): int(value) for key, value in status_counts.items()
            },
            "specialist_eligibility_review_status_counts": {
                str(key): int(value) for key, value in category_counts.items()
            },
            "reference_universe_target_zip_units": len(eligible_references),
            "automatic_paid_follow_up": False,
        }
    )
    remaining = combined.loc[
        combined["current_reference_included"]
        & ~combined["source_union_after_specialist"]
    ].copy()
    _write_csv(specialist_reviewed, outputs["profiles"])
    _write_csv(exact, outputs["exact"])
    _write_csv(exact_market, outputs["exact_market"])
    _write_csv(specialist_matches, outputs["matches"])
    _write_csv(specialist_pairs, outputs["pairs"])
    _write_csv(combined, outputs["union"])
    _write_csv(by_market, outputs["market"])
    _write_csv(remaining, outputs["remaining"])
    _write_json(summary, outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(by_market.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
