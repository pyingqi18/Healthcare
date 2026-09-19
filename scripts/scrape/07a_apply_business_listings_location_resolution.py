"""Apply frozen pilot competition-location decisions without merging rating profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.business_listings_location_resolution import resolve_competition_locations
from medical_ratings.scrape_run_context import add_run_context_arguments, resolve_run_context_arguments


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve pilot competition locations.")
    add_run_context_arguments(parser)
    parser.add_argument("--blocks", type=Path, default=None)
    parser.add_argument("--triage", type=Path, default=None)
    parser.add_argument(
        "--decisions",
        type=Path,
        default=Path("config/business_listings_pilot_location_decisions_20260919.csv"),
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    return resolve_run_context_arguments(
        parser.parse_args(),
        {
            "blocks": (
                "interim",
                "business_listings_pilot_location_audit/"
                "business_listings_location_review_blocks.csv",
            ),
            "triage": (
                "interim",
                "business_listings_pilot_location_triage/"
                "business_listings_location_block_triage.csv",
            ),
            "output_directory": (
                "interim",
                "business_listings_pilot_location_resolution",
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
        "competition": args.output_directory / "business_listings_competition_location_crosswalk.csv",
        "outcomes": args.output_directory / "business_listings_outcome_profile_crosswalk.csv",
        "unresolved": args.output_directory / "business_listings_unresolved_location_blocks.csv",
        "summary": args.output_directory / "business_listings_location_resolution_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )
    blocks = pd.read_csv(args.blocks, dtype={"cid": "string"}, low_memory=False)
    triage = pd.read_csv(args.triage, low_memory=False)
    decisions = pd.read_csv(args.decisions, low_memory=False)
    competition, outcomes, unresolved, summary = resolve_competition_locations(
        blocks, triage, decisions
    )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    _write_csv_atomic(competition, outputs["competition"])
    _write_csv_atomic(outcomes, outputs["outcomes"])
    _write_csv_atomic(unresolved, outputs["unresolved"])
    temporary = outputs["summary"].with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
