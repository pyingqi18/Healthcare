"""Build the complete corrected-data legacy regression report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.legacy_regression_report import build_legacy_regression_report


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate all registered legacy regression tables, descriptive tables, "
            "figures, and one Markdown report."
        )
    )
    parser.add_argument(
        "--panel",
        type=Path,
        default=Path("data/processed/corrected_v1/clinic_year_panel.csv"),
    )
    parser.add_argument(
        "--clinics",
        type=Path,
        default=Path(
            "data/processed/corrected_v1/clinics_eligibility_flagged.csv"
        ),
    )
    parser.add_argument(
        "--strict-panel",
        type=Path,
        default=Path(
            "outputs/legacy_reproduction/corrected_v1/"
            "strict_009a_self_excluded_2mile/"
            "strict_009a_self_excluded_2mile_panel.csv"
        ),
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("outputs/legacy_reproduction/corrected_v1"),
    )
    parser.add_argument(
        "--regions", type=Path, default=Path("config/regions.yaml")
    )
    parser.add_argument(
        "--category-mapping",
        type=Path,
        default=Path("config/google_dental_category_groups.csv"),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("outputs/legacy_reproduction/corrected_v1/report"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    metadata_path = args.output_directory / "legacy_regression_report_metadata.json"
    if metadata_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Report already exists: {metadata_path}. Use --overwrite to replace it."
        )
    regions_payload = yaml.safe_load(args.regions.read_text(encoding="utf-8"))
    regions = regions_payload.get("regions")
    if not isinstance(regions, dict):
        raise TypeError("regions.yaml must contain a regions mapping")
    strict_panel = (
        pd.read_csv(args.strict_panel, low_memory=False)
        if args.strict_panel.exists()
        else None
    )
    category_mapping = (
        pd.read_csv(args.category_mapping, low_memory=False)
        if args.category_mapping.exists()
        else None
    )
    summary = build_legacy_regression_report(
        pd.read_csv(args.panel, low_memory=False),
        pd.read_csv(args.clinics, low_memory=False),
        regions,
        results_root=args.results_root,
        output_directory=args.output_directory,
        strict_panel=strict_panel,
        category_mapping=category_mapping,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
