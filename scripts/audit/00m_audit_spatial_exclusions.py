"""Audit clinics excluded from spatial analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
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
        "--output-directory",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def has_text(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .fillna("")
        .str.strip()
        .ne("")
    )


def count_locations(
    frame: pd.DataFrame,
) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in frame[
            "search_location"
        ]
        .value_counts(dropna=False)
        .items()
    }


def main() -> None:
    args = parse_arguments()

    clinics = pd.read_csv(
        args.clinics,
        dtype="string",
        low_memory=False,
    )

    reviews = pd.read_csv(
        args.reviews,
        usecols=["clinic_key"],
        dtype="string",
        low_memory=False,
    )

    required_columns = {
        "clinic_key",
        "search_location",
        "address",
        "normalized_zip",
        "latitude",
        "longitude",
        "spatial_exclusion_reason",
    }
    missing = required_columns - set(
        clinics.columns
    )

    if missing:
        raise KeyError(
            f"Missing columns: {sorted(missing)}"
        )

    review_counts = (
        reviews.groupby("clinic_key")
        .size()
        .rename("review_rows")
    )

    clinics = clinics.merge(
        review_counts,
        left_on="clinic_key",
        right_index=True,
        how="left",
        validate="one_to_one",
    )
    clinics["review_rows"] = (
        clinics["review_rows"]
        .fillna(0)
        .astype("int64")
    )

    invalid = clinics[
        clinics["spatial_exclusion_reason"]
        == "invalid_or_missing_coordinates"
    ].copy()

    outside = clinics[
        clinics["spatial_exclusion_reason"]
        == "outside_market_distance"
    ].copy()

    latitude = pd.to_numeric(
        invalid["latitude"],
        errors="coerce",
    )
    longitude = pd.to_numeric(
        invalid["longitude"],
        errors="coerce",
    )

    invalid["has_address"] = has_text(
        invalid["address"]
    )
    invalid["has_us_zip"] = (
        invalid["normalized_zip"]
        .astype("string")
        .str.fullmatch(r"\d{5}", na=False)
    )
    invalid["has_geocoding_input"] = (
        invalid["has_address"]
        | invalid["has_us_zip"]
    )

    outside["has_address"] = has_text(
        outside["address"]
    )
    outside["has_us_zip"] = (
        outside["normalized_zip"]
        .astype("string")
        .str.fullmatch(r"\d{5}", na=False)
    )

    summary = {
        "invalid_coordinate_clinic_rows": int(
            len(invalid)
        ),
        "invalid_coordinate_review_rows": int(
            invalid["review_rows"].sum()
        ),
        "missing_latitude_rows": int(
            latitude.isna().sum()
        ),
        "missing_longitude_rows": int(
            longitude.isna().sum()
        ),
        "missing_both_coordinates_rows": int(
            (
                latitude.isna()
                & longitude.isna()
            ).sum()
        ),
        "out_of_range_coordinate_rows": int(
            (
                latitude.notna()
                & longitude.notna()
                & (
                    ~latitude.between(-90, 90)
                    | ~longitude.between(-180, 180)
                )
            ).sum()
        ),
        "zero_coordinate_rows": int(
            (
                (latitude == 0)
                & (longitude == 0)
            ).sum()
        ),
        "invalid_with_address": int(
            invalid["has_address"].sum()
        ),
        "invalid_with_us_zip": int(
            invalid["has_us_zip"].sum()
        ),
        "invalid_with_geocoding_input": int(
            invalid[
                "has_geocoding_input"
            ].sum()
        ),
        "invalid_without_geocoding_input": int(
            (
                ~invalid[
                    "has_geocoding_input"
                ]
            ).sum()
        ),
        "invalid_by_search_location": (
            count_locations(invalid)
        ),
        "outside_market_clinic_rows": int(
            len(outside)
        ),
        "outside_market_review_rows": int(
            outside["review_rows"].sum()
        ),
        "outside_market_with_address": int(
            outside["has_address"].sum()
        ),
        "outside_market_with_us_zip": int(
            outside["has_us_zip"].sum()
        ),
        "outside_market_by_search_location": (
            count_locations(outside)
        ),
    }

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    invalid.to_csv(
        args.output_directory
        / "invalid_coordinate_clinics.csv",
        index=False,
    )
    outside.to_csv(
        args.output_directory
        / "outside_market_clinics.csv",
        index=False,
    )

    summary_path = (
        args.output_directory
        / "spatial_exclusion_summary.json"
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