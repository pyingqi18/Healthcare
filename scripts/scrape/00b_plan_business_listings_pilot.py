"""Build the offline Business Listings pilot plan and coverage audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.business_listings_pilot import (
    build_business_listings_pilot_manifest,
    build_reference_coverage_audit,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan the two-market Business Listings pilot without API calls."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--plan-config",
        type=Path,
        default=Path("config/scrape_plans.yaml"),
    )
    parser.add_argument(
        "--regions",
        type=Path,
        default=Path("config/regions.yaml"),
    )
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
        {"output_directory": ("interim", "business_listings_pilot_plan")},
    )


def read_yaml(path: Path) -> dict[str, object]:
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return content


def main() -> None:
    args = parse_arguments()
    plan_config = read_yaml(args.plan_config)
    regions_config = read_yaml(args.regions)
    category_catalog = pd.read_csv(args.category_catalog, low_memory=False)
    clinics = pd.read_csv(args.clinics, low_memory=False)

    manifest, manifest_summary = build_business_listings_pilot_manifest(
        plan_config,
        regions_config,
        category_catalog,
    )
    coverage, coverage_summary = build_reference_coverage_audit(
        clinics,
        regions_config,
        plan_config["business_listings_pilot"],
    )
    summary = {
        **manifest_summary,
        "reference_coverage": coverage_summary,
        "ready_for_paid_execution": False,
        "remaining_before_execution": [
            "review the four planned requests",
            "implement and test the Business Listings client and parser",
            "add a separate exact paid-confirmation gate",
        ],
    }

    output_paths = {
        "manifest": args.output_directory / "business_listings_pilot_manifest.csv",
        "coverage": args.output_directory / "business_listings_reference_coverage.csv",
        "summary": args.output_directory / "business_listings_pilot_summary.json",
    }
    existing = [path for path in output_paths.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(output_paths["manifest"], index=False)
    coverage.to_csv(output_paths["coverage"], index=False)
    output_paths["summary"].write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
