"""Audit parsed candidates before deduplication and market assignment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.candidate_audit import audit_search_candidates


DEFAULT_RUN_NAME = "rescrape_malone_syracuse_20260907"
DEFAULT_OBSERVATIONS = (
    Path("data/interim") / DEFAULT_RUN_NAME / "clinic_search_observations.csv"
)
DEFAULT_OUTPUT = (
    Path("data/interim") / DEFAULT_RUN_NAME / "clinic_search_candidate_audit.json"
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit candidate overlap, geography, and keyword efficiency."
    )
    parser.add_argument(
        "--observations",
        type=Path,
        default=DEFAULT_OBSERVATIONS,
    )
    parser.add_argument(
        "--regions",
        type=Path,
        default=Path("config/regions.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    observations = pd.read_csv(args.observations, low_memory=False)
    config = yaml.safe_load(args.regions.read_text(encoding="utf-8"))
    regions = config.get("regions")
    if not isinstance(regions, dict):
        raise KeyError("regions.yaml is missing the regions mapping")

    summary = audit_search_candidates(observations, regions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = args.output.with_suffix(f"{args.output.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_path.replace(args.output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Saved aggregate audit: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
