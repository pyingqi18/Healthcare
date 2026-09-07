"""Audit earliest review date coverage before rebuilding entry dates."""

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
        "--output",
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

    if "earliest_review_date" not in clinics.columns:
        raise KeyError(
            "Missing earliest_review_date column"
        )

    parsed = pd.to_datetime(
        clinics["earliest_review_date"],
        errors="coerce",
    )

    valid_count = int(parsed.notna().sum())
    missing_count = int(parsed.isna().sum())
    total_count = len(clinics)

    summary = {
        "premerge_clinic_rows": total_count,
        "valid_earliest_review_dates": valid_count,
        "missing_earliest_review_dates": missing_count,
        "earliest_review_date_coverage": (
            valid_count / total_count
            if total_count
            else None
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