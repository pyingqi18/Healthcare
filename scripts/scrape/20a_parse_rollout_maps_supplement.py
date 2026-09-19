"""Parse and classify the downloaded 15-market Maps core supplement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.maps_supplement import (
    classify_maps_categories,
    deduplicate_maps_by_market,
    keyword_overlap_summary,
    parse_saved_maps_tasks,
)
from medical_ratings.scrape_run_context import add_run_context_arguments, resolve_run_context_arguments


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse the downloaded Maps core supplement without API calls.")
    add_run_context_arguments(parser)
    parser.add_argument("--stage", default="standard_rollout")
    parser.add_argument("--task-log", type=Path, default=None)
    parser.add_argument("--raw-directory", type=Path, default=None)
    parser.add_argument("--category-groups", type=Path, default=Path("config/google_dental_category_groups.csv"))
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    stage = str(args.stage).strip()
    return resolve_run_context_arguments(args, {
        "task_log": ("raw", f"maps_standard_supplement/{stage}/maps_standard_task_log.csv"),
        "raw_directory": ("raw", f"maps_standard_supplement/{stage}/raw"),
        "output_directory": ("interim", f"maps_standard_supplement_parse/{stage}"),
    })


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    summary_path = args.output_directory / "maps_core_parse_summary.json"
    if summary_path.exists() and not args.overwrite:
        raise FileExistsError(f"Output already exists: {summary_path}. Use --overwrite to replace it.")
    observations = parse_saved_maps_tasks(pd.read_csv(args.task_log, low_memory=False), args.raw_directory)
    candidates = deduplicate_maps_by_market(observations)
    classified = classify_maps_categories(candidates, pd.read_csv(args.category_groups))
    overlap = keyword_overlap_summary(classified)
    legacy_priority_counts = classified["legacy_category_group"].value_counts()
    primary_category_counts = classified[
        "primary_legacy_category_group"
    ].value_counts()
    organic = observations["item_type"].eq("maps_search")
    paid = observations["item_type"].eq("maps_paid_item")
    write_csv(observations, args.output_directory / "maps_core_observations.csv")
    write_csv(classified, args.output_directory / "maps_core_candidates.csv")
    write_csv(overlap, args.output_directory / "maps_core_keyword_overlap_by_market.csv")
    summary = {
        "analysis_status": "maps_core_parsed_before_target_zip_and_source_merge",
        "api_requests_submitted": 0,
        "markets_parsed": int(classified["requested_location"].nunique()),
        "paid_tasks_parsed": int(observations["task_id"].nunique()),
        "parsed_observations": len(observations),
        "organic_maps_observations": int(organic.sum()),
        "paid_items_excluded": int(paid.sum()),
        "unique_profiles_within_markets": len(classified),
        "duplicate_keyword_observations_removed": int(organic.sum())
        - len(classified),
        "dentist_only_profiles": int(overlap["dentist_only_profiles"].sum()),
        "dental_clinic_only_profiles": int(overlap["dental_clinic_only_profiles"].sum()),
        "both_keywords_profiles": int(overlap["both_keywords_profiles"].sum()),
        "primary_category_group_counts": {
            str(key): int(value) for key, value in primary_category_counts.items()
        },
        "legacy_any_evidence_priority_group_counts": {
            str(key): int(value) for key, value in legacy_priority_counts.items()
        },
        "priority_group_differs_from_primary_group": int(
            classified["legacy_category_group"]
            .ne(classified["primary_legacy_category_group"])
            .sum()
        ),
        "unclassified_primary_category_profiles": int(
            classified["primary_legacy_category_group"].eq("Unclassified").sum()
        ),
        "interpretation_limit": "Counts are within requested markets before actual-ZIP eligibility and cross-source location resolution.",
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = summary_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(summary_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
