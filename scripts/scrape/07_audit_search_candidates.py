"""Audit parsed candidates before deduplication and market assignment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.candidate_audit import audit_search_candidates
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit candidate overlap, geography, and keyword efficiency."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--observations",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--regions",
        type=Path,
        default=Path("config/regions.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "observations": ("interim", "clinic_search_observations.csv"),
            "output": ("interim", "clinic_search_candidate_audit.json"),
        },
    )


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
