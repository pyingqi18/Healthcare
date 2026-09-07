"""Audit the impact of legacy location-code errors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.geography import (
    add_location_code_status,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit clinics and reviews affected by "
            "incorrect legacy location codes."
        )
    )
    parser.add_argument(
        "--clinics",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--reviews",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--regions",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def load_regions(path: Path) -> dict:
    with path.open(
        "r",
        encoding="utf-8",
    ) as stream:
        config = yaml.safe_load(stream)

    if "regions" not in config:
        raise KeyError(
            "regions.yaml does not contain 'regions'."
        )

    return config["regions"]


def main() -> None:
    args = parse_arguments()

    clinics = pd.read_csv(
        args.clinics,
        dtype={
            "zip": "string",
            "normalized_zip": "string",
            "clinic_key": "string",
        },
        low_memory=False,
    )

    reviews = pd.read_csv(
        args.reviews,
        usecols=["clinic_key"],
        dtype={"clinic_key": "string"},
        low_memory=False,
    )

    required_clinic_columns = {
        "clinic_key",
        "search_location",
        "used_location_code",
    }
    missing_columns = (
        required_clinic_columns
        - set(clinics.columns)
    )

    if missing_columns:
        raise KeyError(
            "Missing clinic columns: "
            f"{sorted(missing_columns)}"
        )

    duplicate_clinic_keys = int(
        clinics["clinic_key"]
        .duplicated(keep=False)
        .sum()
    )

    if duplicate_clinic_keys:
        raise AssertionError(
            "clinics_prepared.csv contains "
            f"{duplicate_clinic_keys} rows with "
            "duplicated clinic_key values."
        )

    regions = load_regions(args.regions)

    clinics_checked = add_location_code_status(
        clinics,
        regions,
    )

    review_counts = (
        reviews.groupby(
            "clinic_key",
            dropna=False,
        )
        .size()
        .rename("review_rows")
    )

    clinics_checked = clinics_checked.merge(
        review_counts,
        left_on="clinic_key",
        right_index=True,
        how="left",
        validate="one_to_one",
    )

    clinics_checked["review_rows"] = (
        clinics_checked["review_rows"]
        .fillna(0)
        .astype("int64")
    )

    known_clinic_keys = set(
        clinics_checked["clinic_key"].dropna()
    )
    review_has_known_clinic = (
        reviews["clinic_key"].isin(
            known_clinic_keys
        )
    )

    mismatches = clinics_checked[
        clinics_checked[
            "location_code_status"
        ]
        == "location_code_mismatch"
    ].copy()

    mismatch_batches = (
        mismatches.groupby(
            [
                "search_location",
                "used_location_code_normalized",
                "expected_location_code",
            ],
            dropna=False,
        )
        .agg(
            clinic_rows=(
                "clinic_key",
                "size",
            ),
            review_rows=(
                "review_rows",
                "sum",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "search_location",
                "used_location_code_normalized",
            ]
        )
    )

    status_counts = (
        clinics_checked[
            "location_code_status"
        ]
        .value_counts(dropna=False)
        .to_dict()
    )

    review_status_counts = (
        clinics_checked.groupby(
            "location_code_status",
            dropna=False,
        )["review_rows"]
        .sum()
        .astype(int)
        .to_dict()
    )

    summary = {
        "input_clinic_rows": int(
            len(clinics)
        ),
        "input_review_rows": int(
            len(reviews)
        ),
        "duplicate_clinic_key_rows": (
            duplicate_clinic_keys
        ),
        "location_code_status_counts": {
            str(key): int(value)
            for key, value
            in status_counts.items()
        },
        "review_rows_by_location_code_status": {
            str(key): int(value)
            for key, value
            in review_status_counts.items()
        },
        "location_code_mismatch_clinic_rows": int(
            len(mismatches)
        ),
        "location_code_mismatch_review_rows": int(
            mismatches["review_rows"].sum()
        ),
        "review_rows_with_known_clinic_key": int(
            review_has_known_clinic.sum()
        ),
        "review_rows_with_unknown_clinic_key": int(
            (~review_has_known_clinic).sum()
        ),
        "mismatch_batches": (
            mismatch_batches.to_dict(
                orient="records"
            )
        ),
    }

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary_path = (
        args.output_directory
        / "location_code_impact_summary.json"
    )
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    mismatch_batches.to_csv(
        args.output_directory
        / "location_code_mismatch_batches.csv",
        index=False,
    )

    mismatch_output_columns = [
        column
        for column in [
            "clinic_key",
            "title",
            "zip",
            "normalized_zip",
            "address",
            "latitude",
            "longitude",
            "search_location",
            "used_location_code",
            "used_location_code_normalized",
            "expected_location_code",
            "location_code_status",
            "review_rows",
        ]
        if column in mismatches.columns
    ]

    mismatches[
        mismatch_output_columns
    ].to_csv(
        args.output_directory
        / "location_code_mismatch_clinics.csv",
        index=False,
    )

    print(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()