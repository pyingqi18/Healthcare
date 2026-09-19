"""Audit Maps actual ZIP eligibility and exact Business Listings overlap."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.maps_supplement import classify_maps_categories
from medical_ratings.maps_supplement_audit import (
    audit_maps_candidates,
    build_business_listings_profile_index,
    compare_maps_with_business_listings,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Maps geography and exact cross-source overlap without API calls."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--stage", default="standard_rollout")
    parser.add_argument("--maps-candidates", type=Path, default=None)
    parser.add_argument("--maps-observations", type=Path, default=None)
    parser.add_argument("--pilot-adjudicated", type=Path, default=None)
    parser.add_argument("--atlanta-eligibility", type=Path, default=None)
    parser.add_argument("--standard-eligibility", type=Path, default=None)
    parser.add_argument("--regions", type=Path, default=Path("config/regions.yaml"))
    parser.add_argument(
        "--category-rules", type=Path, default=Path("config/google_category_rules.csv")
    )
    parser.add_argument(
        "--category-groups",
        type=Path,
        default=Path("config/google_dental_category_groups.csv"),
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    stage = str(args.stage).strip()
    return resolve_run_context_arguments(
        args,
        {
            "maps_candidates": (
                "interim",
                f"maps_standard_supplement_parse/{stage}/maps_core_candidates.csv",
            ),
            "maps_observations": (
                "interim",
                f"maps_standard_supplement_parse/{stage}/maps_core_observations.csv",
            ),
            "pilot_adjudicated": (
                "interim",
                "business_listings_pilot_manual_audit/"
                "business_listings_adjudicated_candidates.csv",
            ),
            "atlanta_eligibility": (
                "interim",
                "business_listings_rollout_market_comparison/"
                "business_listings_rollout_eligibility.csv",
            ),
            "standard_eligibility": (
                "interim",
                "business_listings_rollout_stage_comparison/standard_rollout/"
                "business_listings_rollout_stage_eligibility.csv",
            ),
            "output_directory": (
                "interim",
                f"maps_standard_supplement_audit/{stage}",
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


def main() -> int:
    args = parse_arguments()
    outputs = {
        "profiles": args.output_directory / "maps_core_profile_audit.csv",
        "market": args.output_directory / "maps_core_source_overlap_by_market.csv",
        "maps_only": args.output_directory / "maps_only_profile_review.csv",
        "uncovered": args.output_directory / "maps_uncovered_market_profiles.csv",
        "summary": args.output_directory / "maps_core_source_audit_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    maps_candidates = pd.read_csv(
        args.maps_candidates,
        dtype={"cid": "string", "place_id": "string", "zip": "string"},
        low_memory=False,
    )
    maps_observations = pd.read_csv(
        args.maps_observations,
        dtype={"cid": "string", "place_id": "string", "zip": "string"},
        low_memory=False,
    )
    maps_candidates = classify_maps_categories(
        maps_candidates,
        pd.read_csv(args.category_groups, low_memory=False),
    )
    regions_payload = yaml.safe_load(args.regions.read_text(encoding="utf-8"))
    regions = regions_payload.get("regions")
    if not isinstance(regions, dict):
        raise KeyError("regions.yaml is missing regions")
    maps_reviewed = audit_maps_candidates(
        maps_candidates,
        regions,
        pd.read_csv(args.category_rules, low_memory=False),
    )

    business_index = build_business_listings_profile_index(
        [
            (
                "pilot_adjudicated",
                pd.read_csv(args.pilot_adjudicated, low_memory=False),
            ),
            (
                "atlanta_provisional",
                pd.read_csv(args.atlanta_eligibility, low_memory=False),
            ),
            (
                "standard_rollout_provisional",
                pd.read_csv(args.standard_eligibility, low_memory=False),
            ),
        ]
    )
    compared, market_summary, summary = compare_maps_with_business_listings(
        maps_reviewed, business_index
    )
    organic = maps_observations["item_type"].eq("maps_search")
    paid = maps_observations["item_type"].eq("maps_paid_item")
    organic_task_counts = maps_observations.loc[organic].groupby("task_id").size()
    covered_maps_only = compared.loc[
        compared["business_listings_market_covered"]
        & ~compared["exact_profile_seen_in_business_listings"]
    ]
    summary.update(
        {
            "parsed_observations": len(maps_observations),
            "organic_maps_observations": int(organic.sum()),
            "paid_items_excluded": int(paid.sum()),
            "duplicate_keyword_observations_removed": int(organic.sum())
            - len(maps_candidates),
            "tasks_with_at_least_100_organic_results": int(
                organic_task_counts.ge(100).sum()
            ),
            "primary_category_group_counts": {
                str(key): int(value)
                for key, value in maps_candidates[
                    "primary_legacy_category_group"
                ].value_counts().items()
            },
            "legacy_any_evidence_priority_group_counts": {
                str(key): int(value)
                for key, value in maps_candidates[
                    "legacy_category_group"
                ].value_counts().items()
            },
            "priority_group_differs_from_primary_group": int(
                maps_candidates["legacy_category_group"]
                .ne(maps_candidates["primary_legacy_category_group"])
                .sum()
            ),
            "covered_market_maps_only_provisional_dental_profiles": int(
                covered_maps_only["eligibility_review_status"]
                .eq("include_dental_provider")
                .sum()
            ),
            "covered_market_maps_only_manual_category_review_profiles": int(
                covered_maps_only["eligibility_review_status"]
                .eq("manual_category_review")
                .sum()
            ),
            "covered_market_maps_only_excluded_category_profiles": int(
                covered_maps_only["eligibility_review_status"]
                .eq("exclude_non_dentist_category")
                .sum()
            ),
        }
    )

    maps_only = compared.loc[
        compared["business_listings_market_covered"]
        & compared["maps_source_status"].eq("maps_only_exact_profile")
    ].copy()
    uncovered = compared.loc[
        ~compared["business_listings_market_covered"]
    ].copy()
    write_csv_atomic(compared, outputs["profiles"])
    write_csv_atomic(market_summary, outputs["market"])
    write_csv_atomic(maps_only, outputs["maps_only"])
    write_csv_atomic(uncovered, outputs["uncovered"])
    write_json_atomic(summary, outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
