"""Create a dry-run manifest for exact-CID Business Info backfill tasks."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from medical_ratings.business_info_backfill import (
    build_business_info_manifest,
    summarize_business_info_manifest,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan paid Business Info backfill without submitting tasks."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--reviewed-candidates",
        type=Path,
        default=None,
    )
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
    parser.add_argument("--location-code", type=int, default=2840)
    parser.add_argument("--language-code", default="en")
    parser.add_argument("--priority", type=int, default=1)
    parser.add_argument("--estimated-unit-cost-usd", type=float, default=0.0015)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "reviewed_candidates": ("interim", "clinic_candidate_eligibility_review.csv"),
            "output": ("interim", "business_info_backfill_manifest.csv"),
            "summary": ("interim", "business_info_backfill_manifest_summary.json"),
        },
    )


def main() -> int:
    args = parse_arguments()
    existing = [path for path in (args.output, args.summary) if path.exists()]
    if existing and not args.overwrite:
        paths = ", ".join(str(path) for path in existing)
        raise FileExistsError(
            f"Output already exists: {paths}. Use --overwrite to replace it."
        )

    reviewed = pd.read_csv(args.reviewed_candidates, low_memory=False)
    manifest = build_business_info_manifest(
        reviewed,
        location_code=args.location_code,
        language_code=args.language_code,
        priority=args.priority,
        estimated_unit_cost_usd=args.estimated_unit_cost_usd,
    )
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **summarize_business_info_manifest(manifest),
        "location_codes": sorted(
            int(value) for value in manifest["location_code"].unique()
        ),
        "priorities": sorted(int(value) for value in manifest["priority"].unique()),
        "output": str(args.output),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_manifest = args.output.with_suffix(f"{args.output.suffix}.tmp")
    manifest.to_csv(temporary_manifest, index=False)
    temporary_manifest.replace(args.output)

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
