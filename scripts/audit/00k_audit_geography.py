"""Audit clinic postal codes and geographic locations."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd
import yaml


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--clinics",
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


def haversine_miles(
    latitude: float,
    longitude: float,
    hub_latitude: float,
    hub_longitude: float,
) -> float:
    radius = 3958.7613

    lat1 = math.radians(latitude)
    lat2 = math.radians(hub_latitude)
    delta_lat = math.radians(
        hub_latitude - latitude
    )
    delta_lon = math.radians(
        hub_longitude - longitude
    )

    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    return 2 * radius * math.asin(
        math.sqrt(value)
    )


def classify_postal_code(
    raw_zip: object,
    normalized_zip: object,
) -> str:
    raw_text = (
        ""
        if pd.isna(raw_zip)
        else str(raw_zip).strip()
    )

    if not raw_text:
        return "missing_postal"

    if any(
        character.isalpha()
        for character in raw_text
    ):
        return "non_us_postal"

    normalized_text = (
        ""
        if pd.isna(normalized_zip)
        else str(normalized_zip).strip()
    )

    if (
        len(normalized_text) == 5
        and normalized_text.isdigit()
    ):
        return "us_zip"

    return "invalid_postal"


def main() -> None:
    args = parse_arguments()

    clinics = pd.read_csv(
        args.clinics,
        low_memory=False,
        dtype={
            "zip": "string",
            "normalized_zip": "string",
            "clinic_key": "string",
            "search_location": "string",
        },
    )

    region_config = yaml.safe_load(
        args.regions.read_text(
            encoding="utf-8"
        )
    )

    regions = region_config["regions"]

    clinics["postal_status"] = [
        classify_postal_code(
            raw_zip,
            normalized_zip,
        )
        for raw_zip, normalized_zip in zip(
            clinics["zip"],
            clinics["normalized_zip"],
        )
    ]

    latitude = pd.to_numeric(
        clinics["latitude"],
        errors="coerce",
    )
    longitude = pd.to_numeric(
        clinics["longitude"],
        errors="coerce",
    )

    valid_coordinates = (
        latitude.between(-90, 90)
        & longitude.between(-180, 180)
        & ~(
            latitude.eq(0)
            & longitude.eq(0)
        )
    )

    clinics["valid_coordinates"] = (
        valid_coordinates
    )

    distances: list[float | None] = []
    known_region: list[bool] = []

    for index, row in clinics.iterrows():
        region = regions.get(
            str(row["search_location"])
        )

        if region is None or "hub" not in region:
            known_region.append(False)
            distances.append(None)
            continue

        known_region.append(True)

        if not valid_coordinates.loc[index]:
            distances.append(None)
            continue

        hub_latitude, hub_longitude = (
            region["hub"]
        )

        distances.append(
            haversine_miles(
                float(latitude.loc[index]),
                float(longitude.loc[index]),
                float(hub_latitude),
                float(hub_longitude),
            )
        )

    clinics["known_search_location"] = (
        known_region
    )
    clinics["hub_distance_miles"] = distances

    postal_counts = {
        str(key): int(value)
        for key, value in clinics[
            "postal_status"
        ].value_counts(
            dropna=False
        ).items()
    }

    distance = clinics["hub_distance_miles"]

    summary = {
        "total_clinic_rows": len(clinics),
        "postal_status_counts": postal_counts,
        "valid_coordinate_rows": int(
            valid_coordinates.sum()
        ),
        "invalid_or_missing_coordinate_rows": int(
            (~valid_coordinates).sum()
        ),
        "known_search_location_rows": int(
            clinics[
                "known_search_location"
            ].sum()
        ),
        "unknown_search_location_rows": int(
            (
                ~clinics[
                    "known_search_location"
                ]
            ).sum()
        ),
        "distance_available_rows": int(
            distance.notna().sum()
        ),
        "distance_over_25_miles": int(
            distance.gt(25).sum()
        ),
        "distance_over_50_miles": int(
            distance.gt(50).sum()
        ),
        "distance_over_100_miles": int(
            distance.gt(100).sum()
        ),
        "distance_over_500_miles": int(
            distance.gt(500).sum()
        ),
        "missing_postal_with_valid_coordinates": int(
            (
                clinics["postal_status"].eq(
                    "missing_postal"
                )
                & valid_coordinates
            ).sum()
        ),
        "non_us_postal_with_valid_coordinates": int(
            (
                clinics["postal_status"].eq(
                    "non_us_postal"
                )
                & valid_coordinates
            ).sum()
        ),
        "us_zip_over_100_miles": int(
            (
                clinics["postal_status"].eq(
                    "us_zip"
                )
                & distance.gt(100)
            ).sum()
        ),
    }

    review_required = (
        ~clinics["postal_status"].eq("us_zip")
        | ~valid_coordinates
        | distance.gt(100)
        | ~clinics["known_search_location"]
    )

    review_columns = [
        "clinic_key",
        "title",
        "zip",
        "normalized_zip",
        "address",
        "latitude",
        "longitude",
        "search_location",
        "postal_status",
        "valid_coordinates",
        "known_search_location",
        "hub_distance_miles",
        "entry_date_proxy",
    ]

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    clinics.loc[
        review_required,
        review_columns,
    ].to_csv(
        args.output_directory
        / "geography_review_rows.csv",
        index=False,
    )

    (
        args.output_directory
        / "geography_summary.json"
    ).write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()