"""Audit the Malone and Syracuse replacement without changing processed data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.replacement_audit import (
    audit_replacement_inputs,
    validate_expected_replacement_counts,
)


DEFAULT_RUN_NAME = "rescrape_malone_syracuse_20260907"
DEFAULT_LEGACY_DIRECTORY = Path("data/processed/legacy_v1")
DEFAULT_INTERIM_DIRECTORY = Path("data/interim") / DEFAULT_RUN_NAME


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the exact old rows to remove and new rows to add. "
            "No processed data are changed."
        )
    )
    parser.add_argument(
        "--legacy-clinics",
        type=Path,
        default=DEFAULT_LEGACY_DIRECTORY / "clinics_prepared.csv",
    )
    parser.add_argument(
        "--legacy-reviews",
        type=Path,
        default=DEFAULT_LEGACY_DIRECTORY / "reviews_prepared.csv",
    )
    parser.add_argument(
        "--new-locations",
        type=Path,
        default=DEFAULT_INTERIM_DIRECTORY / "physical_dental_locations_final.csv",
    )
    parser.add_argument(
        "--new-reviews",
        type=Path,
        default=DEFAULT_INTERIM_DIRECTORY / "reviews_parsed.csv",
    )
    parser.add_argument(
        "--zero-review-locations",
        type=Path,
        default=DEFAULT_INTERIM_DIRECTORY / "zero_review_locations.csv",
    )
    parser.add_argument(
        "--batch-output",
        type=Path,
        default=DEFAULT_INTERIM_DIRECTORY / "legacy_replacement_batch_audit.csv",
    )
    parser.add_argument(
        "--collision-output",
        type=Path,
        default=(
            DEFAULT_INTERIM_DIRECTORY
            / "new_unaffected_legacy_collision_review.csv"
        ),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=DEFAULT_INTERIM_DIRECTORY / "replacement_readiness_summary.json",
    )
    return parser.parse_args()


def _read_selected(
    path: Path,
    required: set[str],
    optional: set[str] | None = None,
) -> pd.DataFrame:
    columns = set(pd.read_csv(path, nrows=0).columns)
    missing = required - columns
    if missing:
        raise KeyError(f"{path} is missing columns: {sorted(missing)}")
    selected = required | ((optional or set()) & columns)
    string_columns = {
        column: "string"
        for column in selected
        if column
        in {
            "clinic_key",
            "review_id",
            "final_physical_location_id",
            "zip",
            "normalized_zip",
            "used_location_code",
        }
    }
    return pd.read_csv(
        path,
        usecols=sorted(selected),
        dtype=string_columns,
        low_memory=False,
    )


def _write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _write_json_atomic(content: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(content, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    legacy_clinics = _read_selected(
        args.legacy_clinics,
        {"clinic_key", "title", "zip", "search_location", "used_location_code"},
    )
    legacy_reviews = _read_selected(
        args.legacy_reviews,
        {"clinic_key"},
        {"review_id"},
    )
    new_locations = _read_selected(
        args.new_locations,
        {
            "final_physical_location_id",
            "clinic_key",
            "title",
            "zip",
            "mapped_location",
        },
    )
    new_reviews = _read_selected(
        args.new_reviews,
        {
            "final_physical_location_id",
            "review_id",
            "review_timestamp_utc",
            "rating_value",
            "requested_location",
        },
    )
    zero_review_locations = _read_selected(
        args.zero_review_locations,
        {"final_physical_location_id", "requested_location"},
    )

    batch_audit, collisions, summary = audit_replacement_inputs(
        legacy_clinics,
        legacy_reviews,
        new_locations,
        new_reviews,
        zero_review_locations,
    )
    validate_expected_replacement_counts(summary)
    summary.update(
        {
            "batch_output": str(args.batch_output),
            "collision_output": str(args.collision_output),
            "summary_output": str(args.summary),
        }
    )
    _write_csv_atomic(batch_audit, args.batch_output)
    _write_csv_atomic(collisions, args.collision_output)
    _write_json_atomic(summary, args.summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
