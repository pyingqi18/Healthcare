"""Build one clinic candidate per CID using configured ZIP markets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.clinic_candidates import build_clinic_candidates


DEFAULT_RUN_NAME = "rescrape_malone_syracuse_20260907"
DEFAULT_DIRECTORY = Path("data/interim") / DEFAULT_RUN_NAME


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consolidate search observations into CID candidates."
    )
    parser.add_argument(
        "--observations",
        type=Path,
        default=DEFAULT_DIRECTORY / "clinic_search_observations.csv",
    )
    parser.add_argument(
        "--regions",
        type=Path,
        default=Path("config/regions.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DIRECTORY / "clinic_candidates.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=DEFAULT_DIRECTORY / "clinic_candidates_summary.json",
    )
    return parser.parse_args()


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary_path, index=False)
    temporary_path.replace(path)


def main() -> int:
    args = parse_arguments()
    observations = pd.read_csv(args.observations, low_memory=False)
    config = yaml.safe_load(args.regions.read_text(encoding="utf-8"))
    regions = config.get("regions")
    if not isinstance(regions, dict):
        raise KeyError("regions.yaml is missing the regions mapping")

    candidates = build_clinic_candidates(observations, regions)
    write_csv_atomic(candidates, args.output)
    summary = {
        "input_observations": len(observations),
        "output_candidates": len(candidates),
        "unique_clinic_keys": int(candidates["clinic_key"].nunique()),
        "market_assignment_status": {
            str(key): int(value)
            for key, value in candidates["market_assignment_status"]
            .value_counts()
            .sort_index()
            .items()
        },
        "eligible_by_market": {
            str(key): int(value)
            for key, value in candidates.loc[candidates["target_zip_eligible"]]
            ["mapped_location"]
            .value_counts()
            .sort_index()
            .items()
        },
        "cross_region_search_hits": int(
            candidates["cross_region_search_hit"].sum()
        ),
        "output": str(args.output),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    temporary_summary = args.summary.with_suffix(f"{args.summary.suffix}.tmp")
    temporary_summary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_summary.replace(args.summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
