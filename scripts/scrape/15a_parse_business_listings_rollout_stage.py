"""Parse every pagination-complete market in one Business Listings rollout stage."""

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
        description=(
            "Parse all pagination-complete markets in one rollout stage without "
            "calling the API."
        )
    )
    add_run_context_arguments(parser)
    parser.add_argument("--stage", default="standard_rollout")
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
                "business_listings_rollout_stage_parse",
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
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def select_complete_stage_markets(
    result_log: pd.DataFrame,
    group_completeness: pd.DataFrame,
    *,
    stage: str,
) -> pd.DataFrame:
    """Return one row per complete market with its audited page count."""

    log_required = {"task_tag", "stage", "market", "request_status"}
    missing_log = log_required - set(result_log.columns)
    if missing_log:
        raise KeyError(f"Rollout result log is missing: {sorted(missing_log)}")
    group_required = {
        "market",
        "category_group",
        "saved_page_count",
        "category_group_complete",
    }
    missing_groups = group_required - set(group_completeness.columns)
    if missing_groups:
        raise KeyError(
            f"Group completeness is missing columns: {sorted(missing_groups)}"
        )

    selected_log = result_log.loc[
        result_log["stage"].astype(str).eq(stage)
        & result_log["request_status"].astype(str).eq("completed")
    ].copy()
    if selected_log.empty:
        raise ValueError(f"No completed rollout requests found for stage: {stage}")
    if selected_log["task_tag"].astype(str).duplicated().any():
        raise ValueError("Rollout result log contains duplicate completed task tags")

    markets = sorted(selected_log["market"].astype(str).unique())
    if stage == "standard_rollout" and len(markets) != 10:
        raise ValueError(
            "standard_rollout parsing requires exactly ten completed markets"
        )

    groups = group_completeness.loc[
        group_completeness["market"].astype(str).isin(markets)
    ].copy()
    unexpected = set(groups["market"].astype(str)) - set(markets)
    if unexpected:
        raise ValueError(f"Pagination audit contains unexpected markets: {sorted(unexpected)}")

    records: list[dict[str, object]] = []
    for market in markets:
        market_groups = groups.loc[groups["market"].astype(str).eq(market)].copy()
        if len(market_groups) != 2 or market_groups["category_group"].duplicated().any():
            raise ValueError(f"Pagination audit must contain two groups for {market}")
        complete = (
            market_groups["category_group_complete"]
            .astype(str)
            .str.strip()
            .str.lower()
            .eq("true")
        )
        if not complete.all():
            raise ValueError(f"Pagination audit is incomplete for market: {market}")
        expected_pages = int(
            pd.to_numeric(market_groups["saved_page_count"], errors="raise").sum()
        )
        logged_pages = int(
            selected_log["market"].astype(str).eq(market).sum()
        )
        if logged_pages != expected_pages:
            raise ValueError(
                f"Completed page count differs from pagination audit for {market}: "
                f"log={logged_pages}, audit={expected_pages}"
            )
        records.append(
            {
                "market": market,
                "category_groups": len(market_groups),
                "completed_pages": expected_pages,
            }
        )
    return pd.DataFrame.from_records(records)


def main() -> int:
    args = parse_arguments()
    stage = str(args.stage).strip()
    if not stage:
        raise ValueError("stage cannot be blank")

    result_log_path = args.results_directory / "business_listings_rollout_result_log.csv"
    result_log = pd.read_csv(result_log_path, low_memory=False)
    groups = pd.read_csv(args.group_completeness, low_memory=False)
    market_plan = select_complete_stage_markets(
        result_log,
        groups,
        stage=stage,
    )

    stage_directory = args.output_directory / stage
    all_observations: list[pd.DataFrame] = []
    all_candidates: list[pd.DataFrame] = []
    summaries: list[dict[str, object]] = []
    for row in market_plan.itertuples(index=False):
        market = str(row.market)
        observations = parse_completed_business_listings_results(
            result_log,
            args.results_directory / "raw",
            markets={market},
            expected_completed_requests=int(row.completed_pages),
        )
        candidates = deduplicate_business_listings(observations)
        market_directory = stage_directory / market
        write_csv_atomic(
            observations,
            market_directory / "business_listings_rollout_observations.csv",
        )
        write_csv_atomic(
            candidates,
            market_directory / "business_listings_rollout_candidates.csv",
        )
        market_summary = {
            "market": market,
            "category_groups_parsed": int(row.category_groups),
            "completed_pages_parsed": int(row.completed_pages),
            "parsed_observations": len(observations),
            "unique_profile_candidates": len(candidates),
            "duplicate_observations_removed": len(observations) - len(candidates),
        }
        write_json_atomic(
            {
                "analysis_status": "pagination_complete_rollout_market_parsed",
                **market_summary,
                "api_requests_submitted": 0,
            },
            market_directory / "business_listings_rollout_parse_summary.json",
        )
        summaries.append(market_summary)
        all_observations.append(observations)
        all_candidates.append(candidates)

    combined_observations = pd.concat(all_observations, ignore_index=True)
    combined_candidates = pd.concat(all_candidates, ignore_index=True)
    market_summary_frame = pd.DataFrame.from_records(summaries)
    write_csv_atomic(
        combined_observations,
        stage_directory / "business_listings_rollout_stage_observations.csv",
    )
    write_csv_atomic(
        combined_candidates,
        stage_directory / "business_listings_rollout_stage_candidates.csv",
    )
    write_csv_atomic(
        market_summary_frame,
        stage_directory / "business_listings_rollout_stage_market_summary.csv",
    )
    summary = {
        "analysis_status": "pagination_complete_rollout_stage_parsed",
        "stage": stage,
        "markets_parsed": len(market_plan),
        "category_groups_parsed": int(market_plan["category_groups"].sum()),
        "completed_pages_parsed": int(market_plan["completed_pages"].sum()),
        "parsed_observations": len(combined_observations),
        "unique_profile_candidates_within_markets": len(combined_candidates),
        "duplicate_observations_removed_within_markets": (
            len(combined_observations) - len(combined_candidates)
        ),
        "api_requests_submitted": 0,
    }
    write_json_atomic(
        summary,
        stage_directory / "business_listings_rollout_stage_parse_summary.json",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
