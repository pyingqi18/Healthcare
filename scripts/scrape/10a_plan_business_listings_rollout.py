"""Build the staged 13-market Business Listings plan without API calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.business_listings_rollout import (
    audit_rollout_reference_envelope,
    build_rollout_first_page_plan,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan the staged Business Listings rollout without API calls."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--plan-config", type=Path, default=Path("config/scrape_plans.yaml"))
    parser.add_argument("--regions", type=Path, default=Path("config/regions.yaml"))
    parser.add_argument(
        "--category-catalog",
        type=Path,
        default=Path("config/business_listings_dental_categories.csv"),
    )
    parser.add_argument(
        "--clinics",
        type=Path,
        default=Path("data/processed/corrected_v1/clinics_eligibility_flagged.csv"),
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {"output_directory": ("interim", "business_listings_rollout_plan")},
    )


def read_yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return value


def main() -> int:
    args = parse_arguments()
    plan_config = read_yaml(args.plan_config)
    regions_config = read_yaml(args.regions)
    plan, plan_summary = build_rollout_first_page_plan(
        plan_config,
        regions_config,
        pd.read_csv(args.category_catalog, low_memory=False),
    )
    coverage, coverage_summary = audit_rollout_reference_envelope(
        pd.read_csv(args.clinics, low_memory=False),
        plan,
        regions_config,
    )
    summary = {
        **plan_summary,
        "reference_envelope": coverage_summary,
        "next_action": "Validate the two Atlanta first-page requests before enabling any remaining rollout stage.",
    }
    paths = {
        "plan": args.output_directory / "business_listings_rollout_first_page_plan.csv",
        "coverage": args.output_directory / "business_listings_rollout_reference_coverage.csv",
        "summary": args.output_directory / "business_listings_rollout_plan_summary.json",
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(str(path) for path in existing) + ". Use --overwrite to replace it."
        )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    plan.to_csv(paths["plan"], index=False)
    coverage.to_csv(paths["coverage"], index=False)
    paths["summary"].write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
