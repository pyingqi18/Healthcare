"""Audit candidate fixed-radius competition scales without using outcomes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.spatial_scale_audit import audit_fixed_radius_scales


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize within-market neighbors at fixed radii."
    )
    parser.add_argument("--clinics", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--radii-miles",
        type=float,
        nargs="+",
        default=[1.0, 3.0, 5.0, 10.0, 25.0],
    )
    parser.add_argument("--market-column", default="search_location")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    clinics = pd.read_csv(args.clinics, low_memory=False)
    detail, summary, metadata = audit_fixed_radius_scales(
        clinics,
        args.radii_miles,
        market_column=args.market_column,
    )

    args.output_directory.mkdir(parents=True, exist_ok=True)
    detail.to_csv(
        args.output_directory / "fixed_radius_neighbor_counts.csv",
        index=False,
    )
    summary.to_csv(
        args.output_directory / "fixed_radius_market_summary.csv",
        index=False,
    )
    (args.output_directory / "fixed_radius_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
