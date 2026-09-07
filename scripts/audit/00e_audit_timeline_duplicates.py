"""Audit timeline records that duplicated clinic rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit duplicated timeline matches."
    )
    parser.add_argument(
        "--timeline",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--duplicate-clinics",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    timeline = pd.read_csv(
        args.timeline,
        low_memory=False,
    )
    duplicates = pd.read_csv(
        args.duplicate_clinics,
        low_memory=False,
    )

    required_timeline_columns = {
        "title",
        "est_founded",
    }
    missing = (
        required_timeline_columns
        - set(timeline.columns)
    )

    if missing:
        raise KeyError(
            f"Missing timeline columns: {sorted(missing)}"
        )

    duplicate_titles = set(
        duplicates["title"].dropna().astype(str)
    )

    candidates = timeline[
        timeline["title"]
        .astype(str)
        .isin(duplicate_titles)
    ].copy()

    location_terms = [
        "address",
        "zip",
        "postal",
        "city",
        "state",
        "location",
        "latitude",
        "longitude",
        "lat",
        "lon",
    ]

    location_columns = [
        column
        for column in timeline.columns
        if any(
            term in column.lower()
            for term in location_terms
        )
    ]

    output_columns = list(
        dict.fromkeys(
            [
                "title",
                "est_founded",
                *location_columns,
            ]
        )
    )

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidates[output_columns].to_csv(
        args.output_directory
        / "duplicate_timeline_candidates.csv",
        index=False,
    )

    if candidates.empty:
        titles_with_multiple_rows = 0
        titles_with_conflicting_years = 0
        maximum_rows_per_title = 0
    else:
        row_counts = candidates.groupby(
            "title"
        ).size()

        year_counts = candidates.groupby(
            "title"
        )["est_founded"].nunique(
            dropna=True
        )

        titles_with_multiple_rows = int(
            (row_counts > 1).sum()
        )
        titles_with_conflicting_years = int(
            (year_counts > 1).sum()
        )
        maximum_rows_per_title = int(
            row_counts.max()
        )

    summary = {
        "timeline_total_rows": len(timeline),
        "timeline_columns": timeline.columns.tolist(),
        "location_columns": location_columns,
        "duplicate_clinic_titles": len(
            duplicate_titles
        ),
        "matched_timeline_candidate_rows": len(
            candidates
        ),
        "titles_with_multiple_timeline_rows": (
            titles_with_multiple_rows
        ),
        "titles_with_conflicting_founding_years": (
            titles_with_conflicting_years
        ),
        "maximum_timeline_rows_per_title": (
            maximum_rows_per_title
        ),
    }

    summary_path = (
        args.output_directory
        / "duplicate_timeline_summary.json"
    )

    summary_path.write_text(
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