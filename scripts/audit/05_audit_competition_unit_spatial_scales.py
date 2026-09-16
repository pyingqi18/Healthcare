"""Reproduce frozen fixed-radius diagnostics for provisional address groups."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.competition_unit_spatial_audit import (
    audit_competition_unit_scales,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize fixed-radius neighbors using competition units."
    )
    parser.add_argument("--crosswalk", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--radii-miles",
        type=float,
        nargs="+",
        default=[1.0, 3.0, 5.0, 10.0, 25.0],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    crosswalk = pd.read_csv(args.crosswalk, low_memory=False)
    unit_detail, profile_detail, summary, metadata = (
        audit_competition_unit_scales(crosswalk, args.radii_miles)
    )

    args.output_directory.mkdir(parents=True, exist_ok=True)
    unit_detail.to_csv(
        args.output_directory / "competition_unit_neighbor_counts.csv",
        index=False,
    )
    profile_detail.to_csv(
        args.output_directory / "profile_adjusted_neighbor_counts.csv",
        index=False,
    )
    summary.to_csv(
        args.output_directory / "competition_unit_radius_market_summary.csv",
        index=False,
    )
    (args.output_directory / "competition_unit_radius_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
