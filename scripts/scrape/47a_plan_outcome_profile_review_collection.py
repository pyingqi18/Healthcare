"""Plan one full-rebuild Google Reviews task per eligible outcome profile."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from medical_ratings.review_collection import (
    build_outcome_profile_review_manifest,
    summarize_outcome_profile_review_manifest,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_context_arguments(parser)
    parser.add_argument("--profiles", type=Path, default=None)
    parser.add_argument("--crosswalk", type=Path, default=None)
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--regions", type=Path, default=Path("config/regions.yaml"))
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument(
        "--standard-cost-per-ten-reviews-usd", type=float, default=0.00075
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "profiles": (
                "interim",
                "profile_eligibility_final_application/included_outcome_profiles.csv",
            ),
            "crosswalk": (
                "interim",
                "physical_location_final_freeze/"
                "outcome_profile_competition_location_crosswalk.csv",
            ),
            "output_directory": (
                "interim",
                "outcome_profile_review_collection",
            ),
        },
    )


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    inputs = [args.profiles, args.crosswalk, args.settings, args.regions]
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing review-planning inputs: " + ", ".join(missing))

    manifest_path = args.output_directory / "outcome_profile_review_manifest.csv"
    coverage_path = args.output_directory / "outcome_profile_review_coverage_before_collection.csv"
    summary_path = args.output_directory / "outcome_profile_review_plan_summary.json"
    existing = [
        str(path)
        for path in (manifest_path, coverage_path, summary_path)
        if path.exists()
    ]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(existing) + ". Use --overwrite."
        )

    settings = yaml.safe_load(args.settings.read_text(encoding="utf-8")) or {}
    dataforseo = settings.get("dataforseo")
    if not isinstance(dataforseo, dict):
        raise KeyError("settings.yaml is missing dataforseo")
    region_payload = yaml.safe_load(args.regions.read_text(encoding="utf-8")) or {}
    regions = region_payload.get("regions") or {}
    location_codes = {
        str(name): int(details["location_code"])
        for name, details in regions.items()
    }

    profiles = pd.read_csv(
        args.profiles,
        dtype={"cid": "string", "place_id": "string"},
        low_memory=False,
    )
    crosswalk = pd.read_csv(
        args.crosswalk,
        dtype={"cid": "string"},
        low_memory=False,
    )
    manifest = build_outcome_profile_review_manifest(
        profiles,
        crosswalk,
        location_codes,
        language_code=str(dataforseo["language_code"]),
        sort_by=str(dataforseo["review_sort_by"]),
        depth_minimum=int(dataforseo["review_depth_minimum"]),
        depth_buffer=int(dataforseo["review_depth_buffer"]),
        depth_maximum=int(dataforseo["review_depth_maximum"]),
        depth_multiple=int(dataforseo["review_depth_multiple"]),
        standard_cost_per_ten_reviews_usd=(
            args.standard_cost_per_ten_reviews_usd
        ),
    )
    coverage_columns = [
        "outcome_profile_key",
        "clinic_key",
        "cid",
        "title",
        "requested_location",
        "competition_location_id",
        "address_merge_sensitivity_location_id",
        "reported_votes_count",
        "planned_depth",
        "depth_capped",
        "coverage_status_before_collection",
        "collection_required",
    ]
    coverage = manifest[coverage_columns].copy()
    summary = {
        "analysis_status": "outcome_profile_review_collection_planned",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **summarize_outcome_profile_review_manifest(
            manifest,
            configured_batch_size=int(dataforseo["review_task_batch_size"]),
        ),
        "profile_identity_unit": "one eligible Google outcome profile",
        "competition_identity_unit": "frozen physical competition location",
        "api_depth_limit": 4490,
        "inputs": {
            "profiles": str(args.profiles),
            "crosswalk": str(args.crosswalk),
        },
        "outputs": {
            "manifest": str(manifest_path),
            "coverage_before_collection": str(coverage_path),
            "summary": str(summary_path),
        },
        "next_required_action": (
            "Validate the manifest and quoted cost with the submission script. "
            "No API request was made by this planning stage."
        ),
    }
    _write_csv(manifest, manifest_path)
    _write_csv(coverage, coverage_path)
    _write_json(summary, summary_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
