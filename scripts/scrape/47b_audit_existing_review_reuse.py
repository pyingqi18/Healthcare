"""Audit corrected-v1 review reuse and reduce the paid full-rebuild manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.existing_review_reuse import build_existing_review_reuse_audit
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_context_arguments(parser)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--profiles", type=Path, default=None)
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
    parser.add_argument("--analysis-end-year", type=int, default=2025)
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
            "output_directory": (
                "interim",
                "existing_review_reuse_audit",
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
        args.existing_clinics,
        args.existing_reviews,
    ]
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing review-reuse inputs: " + ", ".join(missing))
    outputs = {
        "existing_audit": args.output_directory / "existing_review_reuse_audit.csv",
        "reusable_existing": args.output_directory / "reusable_existing_profiles.csv",
        "reuse_candidates": args.output_directory / "review_reuse_identity_candidates.csv",
        "reduced_manifest": args.output_directory / "reduced_outcome_profile_review_manifest.csv",
    }
    summary_path = args.output_directory / "existing_review_reuse_summary.json"
    existing = [str(path) for path in [*outputs.values(), summary_path] if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(existing) + ". Use --overwrite."
        )

    manifest = pd.read_csv(
        args.manifest, dtype={"cid": "string", "place_id": "string"}, low_memory=False
    )
    profiles = pd.read_csv(
        args.profiles, dtype={"cid": "string", "place_id": "string", "zip": "string"}, low_memory=False
    )
    clinics = pd.read_csv(
        args.existing_clinics, dtype={"cid": "string", "place_id": "string", "zip": "string"}, low_memory=False
    )
    reviews = pd.read_csv(args.existing_reviews, low_memory=False)
    frames, summary = build_existing_review_reuse_audit(
        manifest,
        profiles,
        clinics,
        reviews,
        analysis_end_year=args.analysis_end_year,
    )
    for key, frame in frames.items():
        _write_csv(frame, outputs[key])
    summary["inputs"] = {
        "manifest": str(args.manifest),
        "profiles": str(args.profiles),
        "existing_clinics": str(args.existing_clinics),
        "existing_reviews": str(args.existing_reviews),
    }
    summary["outputs"] = {
        **{key: str(path) for key, path in outputs.items()},
        "summary": str(summary_path),
    }
    _write_json(summary, summary_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
