"""Parse all 75 saved specialist Maps tasks without API calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.maps_supplement import (
    classify_maps_categories,
    deduplicate_maps_by_market,
    keyword_profile_summary,
    parse_saved_maps_tasks,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse the complete Maps specialist supplement."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--task-log", type=Path, default=None)
    parser.add_argument("--raw-directory", type=Path, default=None)
    parser.add_argument(
        "--category-groups",
        type=Path,
        default=Path("config/google_dental_category_groups.csv"),
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "task_log": (
                "raw",
                "maps_specialist_supplement/maps_specialist_task_log.csv",
            ),
            "raw_directory": ("raw", "maps_specialist_supplement/raw"),
            "output_directory": (
                "interim",
                "maps_specialist_supplement_parse",
            ),
        },
    )


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    summary_path = args.output_directory / "maps_specialist_parse_summary.json"
    if summary_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output already exists: {summary_path}. Use --overwrite to replace it."
        )
    observations = parse_saved_maps_tasks(
        pd.read_csv(args.task_log, low_memory=False),
        args.raw_directory,
        expected_task_count=75,
        expected_market_count=15,
        expected_tasks_per_market=5,
    )
    candidates = deduplicate_maps_by_market(observations)
    classified = classify_maps_categories(
        candidates, pd.read_csv(args.category_groups, low_memory=False)
    )
    by_keyword = keyword_profile_summary(classified)
    organic = observations["item_type"].eq("maps_search")
    paid = observations["item_type"].eq("maps_paid_item")
    primary_counts = classified["primary_legacy_category_group"].value_counts()
    evidence_counts = classified["legacy_category_group"].value_counts()
    _write_csv(
        observations,
        args.output_directory / "maps_specialist_observations.csv",
    )
    _write_csv(
        classified,
        args.output_directory / "maps_specialist_candidates.csv",
    )
    _write_csv(
        by_keyword,
        args.output_directory / "maps_specialist_keyword_profiles_by_market.csv",
    )
    summary = {
        "analysis_status": "maps_specialist_parsed_before_zip_and_source_union",
        "api_requests_submitted": 0,
        "markets_parsed": int(classified["requested_location"].nunique()),
        "paid_tasks_parsed": int(observations["task_id"].nunique()),
        "parsed_observations": len(observations),
        "organic_maps_observations": int(organic.sum()),
        "paid_items_excluded": int(paid.sum()),
        "unique_profiles_within_markets": len(classified),
        "duplicate_keyword_observations_removed": int(organic.sum())
        - len(classified),
        "primary_category_group_counts": {
            str(key): int(value) for key, value in primary_counts.items()
        },
        "legacy_any_evidence_priority_group_counts": {
            str(key): int(value) for key, value in evidence_counts.items()
        },
        "interpretation_limit": (
            "Counts precede actual-ZIP eligibility, cross-source identity review, "
            "and physical-location resolution."
        ),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = summary_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(summary_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
