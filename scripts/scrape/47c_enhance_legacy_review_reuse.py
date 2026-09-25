"""Repair mixed legacy fields and audit stronger zero-cost review reuse."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.enhanced_legacy_review_reuse import (
    build_enhanced_legacy_review_reuse,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_context_arguments(parser)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--profiles", type=Path, default=None)
    parser.add_argument("--stage47b-audit", type=Path, default=None)
    parser.add_argument("--stage47b-reusable", type=Path, default=None)
    parser.add_argument(
        "--existing-clinics",
        type=Path,
        default=Path("data/processed/corrected_v1/clinics_eligibility_flagged.csv"),
    )
    parser.add_argument(
        "--existing-reviews",
        type=Path,
        default=Path("data/processed/corrected_v1/reviews_eligibility_flagged.csv"),
    )
    parser.add_argument("--maximum-coordinate-distance-meters", type=float, default=100.0)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "manifest": (
                "interim",
                "outcome_profile_review_collection/outcome_profile_review_manifest.csv",
            ),
            "profiles": (
                "interim",
                "profile_eligibility_final_application/included_outcome_profiles.csv",
            ),
            "stage47b_audit": (
                "interim",
                "existing_review_reuse_audit/existing_review_reuse_audit.csv",
            ),
            "stage47b_reusable": (
                "interim",
                "existing_review_reuse_audit/reusable_existing_profiles.csv",
            ),
            "output_directory": (
                "interim",
                "enhanced_legacy_review_reuse_audit",
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
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    inputs = [
        args.manifest,
        args.profiles,
        args.stage47b_audit,
        args.stage47b_reusable,
        args.existing_clinics,
        args.existing_reviews,
    ]
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing enhanced reuse inputs: " + ", ".join(missing))
    outputs = {
        "enhanced_audit": args.output_directory / "enhanced_legacy_review_reuse_audit.csv",
        "enhanced_reusable": args.output_directory / "enhanced_reusable_existing_profiles.csv",
        "enhanced_reduced_manifest": args.output_directory / "enhanced_reduced_outcome_profile_review_manifest.csv",
    }
    summary_path = args.output_directory / "enhanced_legacy_review_reuse_summary.json"
    existing = [str(path) for path in [*outputs.values(), summary_path] if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError("Output already exists: " + ", ".join(existing) + ". Use --overwrite.")

    manifest = pd.read_csv(args.manifest, dtype={"cid": "string", "place_id": "string"}, low_memory=False)
    profiles = pd.read_csv(args.profiles, dtype={"cid": "string", "place_id": "string", "zip": "string"}, low_memory=False)
    clinics = pd.read_csv(args.existing_clinics, dtype={"cid": "string", "place_id": "string", "zip": "string"}, low_memory=False)
    reviews = pd.read_csv(args.existing_reviews, low_memory=False)
    audit = pd.read_csv(args.stage47b_audit, low_memory=False)
    reusable = pd.read_csv(args.stage47b_reusable, low_memory=False)
    frames, summary = build_enhanced_legacy_review_reuse(
        manifest,
        profiles,
        clinics,
        reviews,
        audit,
        reusable,
        maximum_coordinate_distance_meters=args.maximum_coordinate_distance_meters,
    )
    for key, frame in frames.items():
        _write_csv(frame, outputs[key])
    summary["inputs"] = {name: str(value) for name, value in vars(args).items() if isinstance(value, Path)}
    summary["outputs"] = {**{key: str(path) for key, path in outputs.items()}, "summary": str(summary_path)}
    _write_json(summary, summary_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
