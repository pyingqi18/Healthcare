"""Build corrected clinic and review tables without overwriting legacy_v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.replacement_audit import (
    audit_replacement_inputs,
    validate_expected_replacement_counts,
)
from medical_ratings.replacement_build import build_corrected_tables


RUN_NAME = "rescrape_malone_syracuse_20260907"
LEGACY_DIRECTORY = Path("data/processed/legacy_v1")
INTERIM_DIRECTORY = Path("data/interim") / RUN_NAME
OUTPUT_DIRECTORY = Path("data/processed/corrected_v1")
EXPECTED_OUTPUT_CLINICS = 5674
EXPECTED_OUTPUT_REVIEWS = 761007


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replace the two wrong legacy batches in a new output directory."
    )
    parser.add_argument(
        "--legacy-clinics",
        type=Path,
        default=LEGACY_DIRECTORY / "clinics_prepared.csv",
    )
    parser.add_argument(
        "--legacy-reviews",
        type=Path,
        default=LEGACY_DIRECTORY / "reviews_prepared.csv",
    )
    parser.add_argument(
        "--new-locations",
        type=Path,
        default=INTERIM_DIRECTORY / "physical_dental_locations_final.csv",
    )
    parser.add_argument(
        "--new-reviews",
        type=Path,
        default=INTERIM_DIRECTORY / "reviews_parsed.csv",
    )
    parser.add_argument(
        "--zero-review-locations",
        type=Path,
        default=INTERIM_DIRECTORY / "zero_review_locations.csv",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=OUTPUT_DIRECTORY,
    )
    return parser.parse_args()


def _write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _write_json_atomic(content: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    legacy_clinics = pd.read_csv(
        args.legacy_clinics,
        low_memory=False,
        dtype={"clinic_key": "string", "zip": "string", "used_location_code": "string"},
    )
    legacy_reviews = pd.read_csv(
        args.legacy_reviews,
        low_memory=False,
        dtype={"clinic_key": "string", "review_id": "string"},
    )
    new_locations = pd.read_csv(
        args.new_locations,
        low_memory=False,
        dtype={"clinic_key": "string", "final_physical_location_id": "string", "zip": "string"},
    )
    new_reviews = pd.read_csv(
        args.new_reviews,
        low_memory=False,
        dtype={"clinic_key": "string", "review_id": "string", "final_physical_location_id": "string"},
    )
    zero_reviews = pd.read_csv(
        args.zero_review_locations,
        low_memory=False,
        dtype={"final_physical_location_id": "string"},
    )

    _, collisions, readiness = audit_replacement_inputs(
        legacy_clinics,
        legacy_reviews,
        new_locations,
        new_reviews,
        zero_reviews,
    )
    validate_expected_replacement_counts(readiness)
    if not readiness["replacement_ready"] or not collisions.empty:
        raise ValueError("Replacement readiness audit has unresolved collisions")

    clinics, reviews, summary = build_corrected_tables(
        legacy_clinics,
        legacy_reviews,
        new_locations,
        new_reviews,
        zero_reviews,
    )
    if summary["output_clinic_rows"] != EXPECTED_OUTPUT_CLINICS:
        raise ValueError("Corrected clinic count does not match the audited total")
    if summary["output_review_rows"] != EXPECTED_OUTPUT_REVIEWS:
        raise ValueError("Corrected review count does not match the audited total")

    clinic_output = args.output_directory / "clinics_prepared.csv"
    review_output = args.output_directory / "reviews_prepared.csv"
    summary_output = args.output_directory / "replacement_summary.json"
    summary.update(
        {
            "clinic_output": str(clinic_output),
            "review_output": str(review_output),
            "summary_output": str(summary_output),
        }
    )
    _write_csv_atomic(clinics, clinic_output)
    _write_csv_atomic(reviews, review_output)
    _write_json_atomic(summary, summary_output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
