"""Reproduce a frozen address-group sensitivity diagnostic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.competition_units import audit_competition_units


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Group exact full-address matches for exposure counts without "
            "merging rating outcomes."
        )
    )
    parser.add_argument("--clinics", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--maximum-address-spread-meters",
        type=float,
        default=50.0,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    clinics = pd.read_csv(args.clinics, low_memory=False)
    crosswalk, market_summary, conflicts, metadata = audit_competition_units(
        clinics,
        maximum_address_spread_meters=args.maximum_address_spread_meters,
    )

    args.output_directory.mkdir(parents=True, exist_ok=True)
    crosswalk.to_csv(
        args.output_directory / "competition_unit_crosswalk.csv",
        index=False,
    )
    market_summary.to_csv(
        args.output_directory / "competition_unit_market_summary.csv",
        index=False,
    )
    conflicts.to_csv(
        args.output_directory / "competition_unit_address_conflicts.csv",
        index=False,
    )
    (args.output_directory / "competition_unit_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
