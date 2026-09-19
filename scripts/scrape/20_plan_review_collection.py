"""Create a dry-run manifest for final-location Google Reviews tasks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.review_collection import (
    build_review_collection_manifest,
    summarize_review_collection_manifest,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan paid Google Reviews tasks without submitting them."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--locations",
        type=Path,
        default=None,
    )
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--regions", type=Path, default=Path("config/regions.yaml"))
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--standard-cost-per-ten-reviews-usd", type=float, default=0.00075
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "locations": ("interim", "physical_dental_locations_final.csv"),
            "output": ("interim", "review_collection_manifest.csv"),
            "summary": ("interim", "review_collection_manifest_summary.json"),
        },
    )


def main() -> int:
    args = parse_arguments()
    existing = [path for path in (args.output, args.summary) if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    settings = yaml.safe_load(args.settings.read_text(encoding="utf-8")) or {}
    if "dataforseo" not in settings:
        raise KeyError("Settings file is missing the dataforseo section")
    region_payload = yaml.safe_load(args.regions.read_text(encoding="utf-8")) or {}
    regions = region_payload.get("regions") or {}
    location_codes = {
        str(name): int(details["location_code"])
        for name, details in regions.items()
    }
    review_settings = settings["dataforseo"]
    locations = pd.read_csv(
        args.locations,
        dtype={"cid": "string", "place_id": "string", "zip": "string"},
        low_memory=False,
    )
    manifest = build_review_collection_manifest(
        locations,
        location_codes,
        language_code=str(review_settings["language_code"]),
        sort_by=str(review_settings["review_sort_by"]),
        depth_minimum=int(review_settings["review_depth_minimum"]),
        depth_buffer=int(review_settings["review_depth_buffer"]),
        depth_maximum=int(review_settings["review_depth_maximum"]),
        depth_multiple=int(review_settings["review_depth_multiple"]),
        standard_cost_per_ten_reviews_usd=(
            args.standard_cost_per_ten_reviews_usd
        ),
    )
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **summarize_review_collection_manifest(
            manifest,
            configured_batch_size=int(review_settings["review_task_batch_size"]),
        ),
        "location_codes": sorted(
            int(value) for value in manifest["location_code"].unique()
        ),
        "sort_by": str(review_settings["review_sort_by"]),
        "output": str(args.output),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = args.output.with_suffix(f"{args.output.suffix}.tmp")
    manifest.to_csv(temporary_output, index=False)
    temporary_output.replace(args.output)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    temporary_summary = args.summary.with_suffix(f"{args.summary.suffix}.tmp")
    temporary_summary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary_summary.replace(args.summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
