"""Audit exact and near co-located clinic identities without merging them."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.coordinate_cluster_audit import audit_coordinate_clusters


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find co-located clinic records before exposure construction."
    )
    parser.add_argument("--clinics", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--distance-threshold-meters",
        type=float,
        default=50.0,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    clinics = pd.read_csv(args.clinics, low_memory=False)
    exact_rows, close_pairs, market_summary, metadata = (
        audit_coordinate_clusters(
            clinics,
            distance_threshold_meters=args.distance_threshold_meters,
        )
    )

    args.output_directory.mkdir(parents=True, exist_ok=True)
    exact_rows.to_csv(
        args.output_directory / "exact_coordinate_cluster_rows.csv",
        index=False,
    )
    close_pairs.to_csv(
        args.output_directory / "close_coordinate_pairs.csv",
        index=False,
    )
    market_summary.to_csv(
        args.output_directory / "coordinate_cluster_market_summary.csv",
        index=False,
    )
    (args.output_directory / "coordinate_cluster_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
