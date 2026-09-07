"""Audit timeline rows missing title or ZIP using location fields."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.identifiers import (
    normalize_name,
    normalize_zip,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--clinics",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--timeline",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def coordinate_key(
    latitude: object,
    longitude: object,
) -> str | None:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None

    if pd.isna(lat) or pd.isna(lon):
        return None

    return f"{lat:.5f}|{lon:.5f}"


def prepare(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()

    result["normalized_title"] = (
        result["title"].map(normalize_name)
    )
    result["normalized_zip"] = (
        result["zip"].map(normalize_zip)
    )
    result["normalized_address"] = (
        result["address"].map(normalize_name)
    )
    result["coordinate_key"] = [
        coordinate_key(lat, lon)
        for lat, lon in zip(
            result["latitude"],
            result["longitude"],
        )
    ]

    result["complete_title_zip"] = (
        result["normalized_title"].notna()
        & result["normalized_zip"].notna()
    )

    return result


def main() -> None:
    args = parse_arguments()

    clinics = prepare(
        pd.read_csv(
            args.clinics,
            low_memory=False,
        )
    )

    timeline = prepare(
        pd.read_csv(
            args.timeline,
            low_memory=False,
        )
    )

    incomplete = timeline.loc[
        ~timeline["complete_title_zip"]
    ].copy()

    audit_rows = []

    for index, row in incomplete.iterrows():
        address_matches = set()
        coordinate_matches = set()

        if pd.notna(row["normalized_address"]):
            address_matches = set(
                clinics.index[
                    clinics["normalized_address"]
                    == row["normalized_address"]
                ]
            )

        if pd.notna(row["coordinate_key"]):
            coordinate_matches = set(
                clinics.index[
                    clinics["coordinate_key"]
                    == row["coordinate_key"]
                ]
            )

        if address_matches and coordinate_matches:
            location_matches = (
                address_matches
                & coordinate_matches
            )
            conflicting_evidence = (
                len(location_matches) == 0
            )
        elif address_matches:
            location_matches = address_matches
            conflicting_evidence = False
        else:
            location_matches = coordinate_matches
            conflicting_evidence = False

        if len(location_matches) == 1:
            status = "unique_location_match"
        elif len(location_matches) > 1:
            status = "multiple_location_matches"
        elif conflicting_evidence:
            status = "conflicting_location_evidence"
        else:
            status = "no_location_match"

        audit_rows.append(
            {
                "timeline_index": index,
                "title": row["title"],
                "zip": row["zip"],
                "address": row["address"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "missing_title": pd.isna(
                    row["normalized_title"]
                ),
                "missing_zip": pd.isna(
                    row["normalized_zip"]
                ),
                "address_match_count": len(
                    address_matches
                ),
                "coordinate_match_count": len(
                    coordinate_matches
                ),
                "location_match_count": len(
                    location_matches
                ),
                "status": status,
            }
        )

    audit = pd.DataFrame(audit_rows)

    summary = {
        "incomplete_timeline_rows": len(incomplete),
        "missing_title_only": int(
            (
                incomplete["normalized_title"].isna()
                & incomplete["normalized_zip"].notna()
            ).sum()
        ),
        "missing_zip_only": int(
            (
                incomplete["normalized_title"].notna()
                & incomplete["normalized_zip"].isna()
            ).sum()
        ),
        "missing_both": int(
            (
                incomplete["normalized_title"].isna()
                & incomplete["normalized_zip"].isna()
            ).sum()
        ),
        "unique_location_matches": int(
            (
                audit["status"]
                == "unique_location_match"
            ).sum()
        ),
        "multiple_location_matches": int(
            (
                audit["status"]
                == "multiple_location_matches"
            ).sum()
        ),
        "conflicting_location_evidence": int(
            (
                audit["status"]
                == "conflicting_location_evidence"
            ).sum()
        ),
        "no_location_match": int(
            (
                audit["status"]
                == "no_location_match"
            ).sum()
        ),
    }

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit.to_csv(
        args.output_directory
        / "incomplete_timeline_audit.csv",
        index=False,
    )

    (
        args.output_directory
        / "incomplete_timeline_summary.json"
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