"""Prioritize multi-profile Business Listings blocks for manual review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.business_listings_location_triage import triage_location_blocks
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Triage multi-profile location blocks.")
    add_run_context_arguments(parser)
    parser.add_argument("--blocks", type=Path, default=None)
    parser.add_argument("--pairs", type=Path, default=None)
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
            "pairs": (
                "interim",
                "business_listings_pilot_location_audit/"
                "business_listings_location_review_pairs.csv",
            ),
            "output_directory": (
                "interim",
                "business_listings_pilot_location_triage",
            ),
        },
    )


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    outputs = {
        "blocks": args.output_directory / "business_listings_location_block_triage.csv",
        "profiles": args.output_directory / "business_listings_location_profiles_by_tier.csv",
        "summary": args.output_directory / "business_listings_location_triage_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )
    blocks = pd.read_csv(args.blocks, dtype={"cid": "string"}, low_memory=False)
    pairs = pd.read_csv(
        args.pairs,
        dtype={"left_cid": "string", "right_cid": "string"},
        low_memory=False,
    )
    block_summary, profiles, summary = triage_location_blocks(blocks, pairs)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(block_summary, outputs["blocks"])
    write_csv_atomic(profiles, outputs["profiles"])
    temporary = outputs["summary"].with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

