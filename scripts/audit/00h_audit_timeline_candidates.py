"""Audit candidate clinic identities for incomplete timeline rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.identifiers import (
    build_clinic_key,
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

    return result


def candidate_identity(row: pd.Series) -> str:
    try:
        return build_clinic_key(row.to_dict())
    except (TypeError, ValueError):
        return "|".join(
            [
                str(row.get("normalized_title") or ""),
                str(row.get("normalized_zip") or ""),
                str(row.get("normalized_address") or ""),
                str(row.get("coordinate_key") or ""),
            ]
        )


def main() -> None:
    args = parse_arguments()

    parse_arguments()

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

    incomplete_timeline = timeline.loc[
        timeline["normalized_title"].isna()
        | timeline["normalized_zip"].isna()
    ].copy()

    clinic_missing_title_only = int(
        (
            clinics["normalized_title"].isna()
            & clinics["normalized_zip"].notna()
        ).sum()
    )
    clinic_missing_zip_only = int(
        (
            clinics["normalized_title"].notna()
            & clinics["normalized_zip"].isna()
        ).sum()
    )
    clinic_missing_both = int(
        (
            clinics["normalized_title"].isna()
            & clinics["normalized_zip"].isna()
        ).sum()
    )

    timeline_results = []
    candidate_rows = []

    for timeline_index, row in (
        incomplete_timeline.iterrows()
    ):
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
            candidates = (
                address_matches
                & coordinate_matches
            )
        elif address_matches:
            candidates = address_matches
        else:
            candidates = coordinate_matches

        identities = set()

        for clinic_index in sorted(candidates):
            clinic = clinics.loc[clinic_index]
            identity = candidate_identity(clinic)
            identities.add(identity)

            candidate_rows.append(
                {
                    "timeline_index": timeline_index,
                    "clinic_index": clinic_index,
                    "timeline_title": row["title"],
                    "timeline_est_founded": row.get(
                        "est_founded"
                    ),
                    "clinic_title": clinic["title"],
                    "clinic_zip": clinic["zip"],
                    "clinic_address": clinic["address"],
                    "clinic_latitude": clinic["latitude"],
                    "clinic_longitude": clinic["longitude"],
                    "clinic_category": clinic.get(
                        "category"
                    ),
                    "candidate_clinic_key": identity,
                }
            )

        if len(candidates) == 0:
            status = "no_candidate"
        elif len(identities) == 1:
            status = "one_clinic_identity"
        else:
            status = "multiple_clinic_identities"

        timeline_results.append(
            {
                "timeline_index": timeline_index,
                "timeline_title": row["title"],
                "timeline_est_founded": row.get(
                    "est_founded"
                ),
                "candidate_row_count": len(candidates),
                "candidate_identity_count": len(
                    identities
                ),
                "status": status,
            }
        )

    result = pd.DataFrame(timeline_results)

    summary = {
        "premerge_missing_title_only": (
            clinic_missing_title_only
        ),
        "premerge_missing_zip_only": (
            clinic_missing_zip_only
        ),
        "premerge_missing_both": (
            clinic_missing_both
        ),
        "incomplete_timeline_rows": len(
            incomplete_timeline
        ),
        "timeline_rows_with_one_clinic_identity": int(
            (
                result["status"]
                == "one_clinic_identity"
            ).sum()
        ),
        "timeline_rows_with_multiple_clinic_identities": int(
            (
                result["status"]
                == "multiple_clinic_identities"
            ).sum()
        ),
        "timeline_rows_with_no_candidate": int(
            (
                result["status"]
                == "no_candidate"
            ).sum()
        ),
        "total_candidate_rows": int(
            result["candidate_row_count"].sum()
        ),
        "total_candidate_identities": int(
            result["candidate_identity_count"].sum()
        ),
    }

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        args.output_directory
        / "incomplete_timeline_candidate_summary.csv",
        index=False,
    )

    pd.DataFrame(candidate_rows).to_csv(
        args.output_directory
        / "incomplete_timeline_candidate_rows.csv",
        index=False,
    )

    (
        args.output_directory
        / "incomplete_timeline_candidate_summary.json"
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