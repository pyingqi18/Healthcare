"""Add analysis eligibility flags to legacy data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.geography import (
    add_analysis_eligibility,
)

from medical_ratings.spatial import (
    add_spatial_eligibility,
)



def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Add analysis eligibility flags to "
            "prepared legacy clinics and reviews."
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
    parser.add_argument(
        "--diagnostics-directory",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--max-hub-distance-miles",
        type=float,
        default=100.0,
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


def count_values(
    series: pd.Series,
) -> dict[str, int]:
    counts = series.value_counts(
        dropna=False
    )

    return {
        str(key): int(value)
        for key, value in counts.items()
    }


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
        dtype={
            "shop_zip": "string",
            "normalized_review_zip": "string",
            "clinic_key": "string",
        },
        low_memory=False,
    )

    required_clinic_columns = {
        "clinic_key",
        "search_location",
        "used_location_code",
        "zip",
    }
    missing_clinic_columns = (
        required_clinic_columns
        - set(clinics.columns)
    )

    if missing_clinic_columns:
        raise KeyError(
            "Missing clinic columns: "
            f"{sorted(missing_clinic_columns)}"
        )

    if "clinic_key" not in reviews.columns:
        raise KeyError(
            "reviews_prepared.csv is missing "
            "clinic_key."
        )

    duplicate_clinic_rows = int(
        clinics["clinic_key"]
        .duplicated(keep=False)
        .sum()
    )

    if duplicate_clinic_rows:
        raise AssertionError(
            "Clinic keys are not unique. "
            f"Duplicate rows: {duplicate_clinic_rows}"
        )

    missing_clinic_keys = int(
        clinics["clinic_key"].isna().sum()
    )

    if missing_clinic_keys:
        raise AssertionError(
            "Prepared clinics contain missing "
            f"clinic_key values: {missing_clinic_keys}"
        )

    known_clinic_keys = set(
        clinics["clinic_key"]
    )

    unknown_review_key = (
        reviews["clinic_key"].isna()
        | ~reviews["clinic_key"].isin(
            known_clinic_keys
        )
    )

    unknown_review_rows = int(
        unknown_review_key.sum()
    )

    if unknown_review_rows:
        raise AssertionError(
            "Reviews contain missing or unknown "
            f"clinic_key values: {unknown_review_rows}"
        )

    regions = load_regions(args.regions)

    clinics_flagged = (
        add_analysis_eligibility(
            clinics,
            regions,
        )
    )

    clinics_flagged = add_spatial_eligibility(
        clinics_flagged,
        regions,
        max_hub_distance_miles=(
            args.max_hub_distance_miles
        ),
    )

    clinic_status = (
        clinics_flagged.set_index(
            "clinic_key"
        )[
            [
                "expected_location_code",
                "used_location_code_normalized",
                "location_code_status",
                "analysis_exclusion_reason",
                "preliminary_analysis_eligible",
                "valid_coordinates",
                "hub_distance_miles",
                "spatial_exclusion_reason",
                "spatial_analysis_eligible",
            ]
        ]
    )

    reviews_flagged = reviews.copy()

    for column in clinic_status.columns:
        reviews_flagged[column] = (
            reviews_flagged["clinic_key"]
            .map(clinic_status[column])
        )

    missing_review_status = int(
        reviews_flagged[
            "analysis_exclusion_reason"
        ]
        .isna()
        .sum()
    )

    if missing_review_status:
        raise AssertionError(
            "Some reviews did not receive "
            "eligibility status: "
            f"{missing_review_status}"
        )

    clinic_eligible_rows = int(
        clinics_flagged[
            "preliminary_analysis_eligible"
        ].sum()
    )
    review_eligible_rows = int(
        reviews_flagged[
            "preliminary_analysis_eligible"
        ].sum()
    )

    spatial_eligible_clinic_rows = int(
        clinics_flagged[
            "spatial_analysis_eligible"
        ].sum()
    )

    spatial_eligible_review_rows = int(
        reviews_flagged[
            "spatial_analysis_eligible"
        ].sum()
    )

    summary = {
        "input_clinic_rows": int(
            len(clinics)
        ),
        "output_clinic_rows": int(
            len(clinics_flagged)
        ),
        "input_review_rows": int(
            len(reviews)
        ),
        "output_review_rows": int(
            len(reviews_flagged)
        ),
        "duplicate_clinic_key_rows": (
            duplicate_clinic_rows
        ),
        "unknown_review_clinic_key_rows": (
            unknown_review_rows
        ),
        "clinic_exclusion_reason_counts": (
            count_values(
                clinics_flagged[
                    "analysis_exclusion_reason"
                ]
            )
        ),
        "review_exclusion_reason_counts": (
            count_values(
                reviews_flagged[
                    "analysis_exclusion_reason"
                ]
            )
        ),
        "preliminary_eligible_clinic_rows": (
            clinic_eligible_rows
        ),
        "preliminary_excluded_clinic_rows": int(
            len(clinics_flagged)
            - clinic_eligible_rows
        ),
        "preliminary_eligible_review_rows": (
            review_eligible_rows
        ),
        "preliminary_excluded_review_rows": int(
            len(reviews_flagged)
            - review_eligible_rows
        ),
        "spatial_clinic_reason_counts": (
            count_values(
                clinics_flagged[
                    "spatial_exclusion_reason"
                ]
            )
        ),
        "spatial_review_reason_counts": (
            count_values(
                reviews_flagged[
                    "spatial_exclusion_reason"
                ]
            )
        ),
        "spatial_eligible_clinic_rows": (
            spatial_eligible_clinic_rows
        ),
        "spatial_excluded_clinic_rows": int(
            len(clinics_flagged)
            - spatial_eligible_clinic_rows
        ),
        "spatial_eligible_review_rows": (
            spatial_eligible_review_rows
        ),
        "spatial_excluded_review_rows": int(
            len(reviews_flagged)
            - spatial_eligible_review_rows
        ),
    }

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.diagnostics_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    clinics_output = (
        args.output_directory
        / "clinics_eligibility_flagged.csv"
    )
    reviews_output = (
        args.output_directory
        / "reviews_eligibility_flagged.csv"
    )

    clinics_flagged.to_csv(
        clinics_output,
        index=False,
    )
    reviews_flagged.to_csv(
        reviews_output,
        index=False,
    )

    summary_path = (
        args.diagnostics_directory
        / "eligibility_summary.json"
    )
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
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