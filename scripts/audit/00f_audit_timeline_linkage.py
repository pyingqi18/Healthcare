"""Audit title and ZIP linkage between clinics and timeline data."""

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
    parser = argparse.ArgumentParser(
        description=(
            "Audit title and ZIP linkage between "
            "premerge clinics and timeline data."
        )
    )
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
        "--output",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def add_title_zip_key(
    data: pd.DataFrame,
) -> pd.DataFrame:
    result = data.copy()

    result["normalized_title"] = (
        result["title"].map(normalize_name)
    )
    result["normalized_zip"] = (
        result["zip"].map(normalize_zip)
    )

    result["has_complete_title_zip"] = (
        result["normalized_title"].notna()
        & result["normalized_zip"].notna()
    )

    result["title_zip_key"] = pd.Series(
        pd.NA,
        index=result.index,
        dtype="string",
    )

    complete = result["has_complete_title_zip"]

    result.loc[complete, "title_zip_key"] = (
        result.loc[complete, "normalized_title"]
        + "|"
        + result.loc[complete, "normalized_zip"]
    )

    return result


def duplicate_summary(
    data: pd.DataFrame,
) -> tuple[int, int]:
    complete_keys = data.loc[
        data["has_complete_title_zip"],
        "title_zip_key",
    ]

    duplicated = complete_keys.duplicated(
        keep=False
    )

    duplicate_rows = int(duplicated.sum())
    duplicate_keys = int(
        complete_keys[duplicated].nunique()
    )

    return duplicate_rows, duplicate_keys


def main() -> None:
    args = parse_arguments()

    clinics = pd.read_csv(
        args.clinics,
        low_memory=False,
    )
    timeline = pd.read_csv(
        args.timeline,
        low_memory=False,
    )

    required_columns = {"title", "zip"}

    for label, data in {
        "clinics": clinics,
        "timeline": timeline,
    }.items():
        missing = required_columns - set(data.columns)

        if missing:
            raise KeyError(
                f"{label} is missing columns: "
                f"{sorted(missing)}"
            )

    clinics = add_title_zip_key(clinics)
    timeline = add_title_zip_key(timeline)

    timeline_key_counts = (
        timeline["title_zip_key"].value_counts()
    )

    clinic_match_counts = (
        clinics["title_zip_key"]
        .map(timeline_key_counts)
        .fillna(0)
        .astype(int)
    )

    clinic_duplicate_rows, clinic_duplicate_keys = (
        duplicate_summary(clinics)
    )

    timeline_duplicate_rows, timeline_duplicate_keys = (
        duplicate_summary(timeline)
    )

    summary = {
        "premerge_clinic_rows": len(clinics),
        "timeline_rows": len(timeline),
        "premerge_missing_title_or_zip": int(
            (
                clinics["normalized_title"].isna()
                | clinics["normalized_zip"].isna()
            ).sum()
        ),
        "timeline_missing_title_or_zip": int(
            (
                timeline["normalized_title"].isna()
                | timeline["normalized_zip"].isna()
            ).sum()
        ),
        "premerge_duplicate_title_zip_rows": (
            clinic_duplicate_rows
        ),
        "premerge_duplicate_title_zip_keys": (
            clinic_duplicate_keys
        ),
        "timeline_duplicate_title_zip_rows": (
            timeline_duplicate_rows
        ),
        "timeline_duplicate_title_zip_keys": (
            timeline_duplicate_keys
        ),
        "clinics_with_exactly_one_timeline_match": int(
            (clinic_match_counts == 1).sum()
        ),
        "clinics_with_multiple_timeline_matches": int(
            (clinic_match_counts > 1).sum()
        ),
        "clinics_with_no_timeline_match": int(
            (clinic_match_counts == 0).sum()
        ),
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
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