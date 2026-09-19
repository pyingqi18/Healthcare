"""Parse one pagination-complete Business Listings rollout market."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.business_listings_live import (
    deduplicate_business_listings,
    parse_completed_business_listings_results,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse one complete Business Listings rollout market without API calls."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--market", default="Atlanta_GA_L")
    parser.add_argument("--results-directory", type=Path, default=None)
    parser.add_argument("--group-completeness", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "results_directory": ("raw", "business_listings_rollout"),
            "group_completeness": (
                "interim",
                "business_listings_rollout_pagination_audit/"
                "business_listings_group_completeness.csv",
            ),
            "output_directory": (
                "interim",
                "business_listings_rollout_market_parse",
            ),
        },
    )


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    market = str(args.market).strip()
    if not market:
        raise ValueError("market cannot be blank")
    groups = pd.read_csv(args.group_completeness, low_memory=False)
    required = {
        "market",
        "category_group",
        "saved_page_count",
        "category_group_complete",
    }
    missing = required - set(groups.columns)
    if missing:
        raise KeyError(f"Group completeness is missing columns: {sorted(missing)}")
    selected_groups = groups.loc[groups["market"].astype(str).eq(market)].copy()
    if selected_groups.empty:
        raise ValueError(f"Pagination audit does not contain market: {market}")
    complete = (
        selected_groups["category_group_complete"]
        .astype(str)
        .str.strip()
        .str.lower()
        .eq("true")
    )
    if not complete.all():
        raise ValueError(f"Pagination audit is incomplete for market: {market}")
    if selected_groups["category_group"].duplicated().any():
        raise ValueError("Pagination audit contains duplicate category groups")
    expected_pages = int(
        pd.to_numeric(selected_groups["saved_page_count"], errors="raise").sum()
    )

    result_log_path = args.results_directory / "business_listings_rollout_result_log.csv"
    observations = parse_completed_business_listings_results(
        pd.read_csv(result_log_path, low_memory=False),
        args.results_directory / "raw",
        markets={market},
        expected_completed_requests=expected_pages,
    )
    candidates = deduplicate_business_listings(observations)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    observations_path = args.output_directory / "business_listings_rollout_observations.csv"
    candidates_path = args.output_directory / "business_listings_rollout_candidates.csv"
    summary_path = args.output_directory / "business_listings_rollout_parse_summary.json"
    write_csv_atomic(observations, observations_path)
    write_csv_atomic(candidates, candidates_path)
    summary = {
        "analysis_status": "pagination_complete_rollout_market_parsed",
        "market": market,
        "category_groups_parsed": len(selected_groups),
        "completed_pages_parsed": expected_pages,
        "parsed_observations": len(observations),
        "unique_profile_candidates": len(candidates),
        "duplicate_observations_removed": len(observations) - len(candidates),
        "api_requests_submitted": 0,
    }
    temporary = summary_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(summary_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
