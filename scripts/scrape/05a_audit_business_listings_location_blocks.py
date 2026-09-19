"""Create manual-review blocks for Business Listings competition profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.business_listings_location_audit import (
    build_business_listings_location_audit,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build review-only profile-to-location evidence blocks."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    return resolve_run_context_arguments(
        parser.parse_args(),
        {
            "candidates": (
                "interim",
                "business_listings_pilot_manual_audit/"
                "business_listings_adjudicated_candidates.csv",
            ),
            "output_directory": (
                "interim",
                "business_listings_pilot_location_audit",
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
        "pairs": args.output_directory / "business_listings_location_review_pairs.csv",
        "blocks": args.output_directory / "business_listings_location_review_blocks.csv",
        "summary": args.output_directory / "business_listings_location_audit_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    candidates = pd.read_csv(
        args.candidates,
        dtype={"cid": "string", "place_id": "string", "zip": "string"},
        low_memory=False,
    )
    pairs, blocks, summary = build_business_listings_location_audit(candidates)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(pairs, outputs["pairs"])
    write_csv_atomic(blocks, outputs["blocks"])
    temporary = outputs["summary"].with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

