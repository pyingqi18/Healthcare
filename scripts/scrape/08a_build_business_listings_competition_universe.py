"""Build the final two-market competition universe after location resolution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.business_listings_competition_universe import (
    build_pilot_competition_universe,
)
from medical_ratings.scrape_run_context import add_run_context_arguments, resolve_run_context_arguments


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the pilot competition universe.")
    add_run_context_arguments(parser)
    parser.add_argument("--location-crosswalk", type=Path, default=None)
    parser.add_argument("--location-blocks", type=Path, default=None)
    parser.add_argument("--adjudicated-references", type=Path, default=None)
    parser.add_argument(
        "--carry-forwards",
        type=Path,
        default=Path("config/business_listings_pilot_carry_forward_locations_20260919.csv"),
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    return resolve_run_context_arguments(
        parser.parse_args(),
        {
            "location_crosswalk": (
                "interim",
                "business_listings_pilot_location_resolution/"
                "business_listings_competition_location_crosswalk.csv",
            ),
            "location_blocks": (
                "interim",
                "business_listings_pilot_location_audit/"
                "business_listings_location_review_blocks.csv",
            ),
            "adjudicated_references": (
                "interim",
                "business_listings_pilot_manual_audit/"
                "business_listings_adjudicated_references.csv",
            ),
            "output_directory": (
                "interim",
                "business_listings_pilot_competition_universe",
            ),
        },
    )


def _write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    outputs = {
        "locations": args.output_directory / "business_listings_pilot_competition_locations.csv",
        "profiles": args.output_directory / "business_listings_pilot_profile_location_crosswalk.csv",
        "summary": args.output_directory / "business_listings_pilot_competition_universe_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )
    location_crosswalk = pd.read_csv(args.location_crosswalk, low_memory=False)
    location_blocks = pd.read_csv(args.location_blocks, dtype={"cid": "string"}, low_memory=False)
    references = pd.read_csv(args.adjudicated_references, low_memory=False)
    carry_forwards = pd.read_csv(args.carry_forwards, dtype={"zip": "string"}, low_memory=False)
    locations, profiles, summary = build_pilot_competition_universe(
        location_crosswalk, location_blocks, references, carry_forwards
    )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    _write_csv_atomic(locations, outputs["locations"])
    _write_csv_atomic(profiles, outputs["profiles"])
    temporary = outputs["summary"].with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
