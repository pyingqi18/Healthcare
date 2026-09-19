"""Audit saved NYC/LA first pages before approving paid continuations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.business_listings_live import (
    parse_completed_business_listings_results,
)
from medical_ratings.business_listings_rollout import (
    audit_major_metro_first_pages,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit saved NYC/LA first-page ZIP yield without API calls."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--results-directory", type=Path, default=None)
    parser.add_argument("--group-completeness", type=Path, default=None)
    parser.add_argument("--regions", type=Path, default=Path("config/regions.yaml"))
    parser.add_argument(
        "--plan-config", type=Path, default=Path("config/scrape_plans.yaml")
    )
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
                "business_listings_major_metro_scope_audit",
            ),
        },
    )


def read_yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return value


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    markets = {"NYC_NY_L", "LA_CA_L"}
    result_log_path = (
        args.results_directory / "business_listings_rollout_result_log.csv"
    )
    result_log = pd.read_csv(result_log_path, low_memory=False)
    first_pages = result_log.loc[
        result_log["market"].astype(str).isin(markets)
        & result_log["task_tag"].astype(str).str.endswith(":p01")
    ].copy()
    observations = parse_completed_business_listings_results(
        first_pages,
        args.results_directory / "raw",
        markets=markets,
        expected_completed_requests=4,
    )
    pricing = read_yaml(args.plan_config).get("pricing")
    if not isinstance(pricing, dict):
        raise KeyError("scrape_plans.yaml is missing pricing")
    annotated, group_scope, summary = audit_major_metro_first_pages(
        observations,
        pd.read_csv(args.group_completeness, low_memory=False),
        read_yaml(args.regions),
        request_cost_usd=float(pricing["business_listings_live_per_request"]),
        item_cost_usd=float(pricing["business_listings_live_per_item"]),
    )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(
        annotated,
        args.output_directory / "major_metro_first_page_observations.csv",
    )
    write_csv_atomic(
        group_scope,
        args.output_directory / "major_metro_first_page_scope_by_group.csv",
    )
    summary_path = args.output_directory / "major_metro_first_page_scope_summary.json"
    temporary = summary_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(summary_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(group_scope.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
