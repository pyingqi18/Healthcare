"""Prepare a location-safe clinic table from legacy data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.legacy import (
    prepare_legacy_clinics,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare legacy clinic data."
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
    parser.add_argument(
        "--summary",
        type=Path,
        required=True,
    )
    return parser.parse_args()


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

    prepared = prepare_legacy_clinics(
        clinics,
        timeline,
    )

    if len(prepared) != len(clinics):
        raise ValueError(
            "Clinic row count changed during preparation. "
            f"Input rows: {len(clinics)}. "
            f"Output rows: {len(prepared)}."
        )

    if prepared["clinic_key"].duplicated().any():
        raise ValueError(
            "Prepared clinic_key values are not unique"
        )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.summary.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    prepared.to_csv(
        args.output,
        index=False,
    )

    match_counts = (
        prepared["timeline_match_method"]
        .value_counts(dropna=False)
        .to_dict()
    )

    source_counts = (
        prepared["entry_date_source"]
        .value_counts(dropna=False)
        .to_dict()
    )

    valid_entry_dates = int(
        prepared["entry_date_proxy"].notna().sum()
    )

    summary = {
        "input_clinic_rows": len(clinics),
        "timeline_rows": len(timeline),
        "output_clinic_rows": len(prepared),
        "unique_clinic_keys": int(
            prepared["clinic_key"].nunique()
        ),
        "duplicate_clinic_keys": int(
            prepared["clinic_key"]
            .duplicated(keep=False)
            .sum()
        ),
        "timeline_match_counts": {
            str(key): int(value)
            for key, value in match_counts.items()
        },
        "valid_website_founded_dates": int(
            prepared[
                "website_founded_date_proxy"
            ].notna().sum()
        ),
        "valid_earliest_review_dates": int(
            prepared[
                "earliest_review_date_parsed"
            ].notna().sum()
        ),
        "valid_entry_dates": valid_entry_dates,
        "missing_entry_dates": int(
            prepared[
                "entry_date_proxy"
            ].isna().sum()
        ),
        "entry_date_coverage": (
            valid_entry_dates / len(prepared)
            if len(prepared)
            else None
        ),
        "entry_date_source_counts": {
            str(key): int(value)
            for key, value in source_counts.items()
        },
    }

    args.summary.write_text(
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