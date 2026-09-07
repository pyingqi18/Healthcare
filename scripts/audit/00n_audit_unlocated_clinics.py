"""Audit location evidence for clinics without coordinates."""

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


def nonmissing(series: pd.Series) -> pd.Series:
    text = (
        series.astype("string")
        .fillna("")
        .str.strip()
        .str.lower()
    )
    return ~text.isin(
        ["", "nan", "none", "<na>"]
    )


def boolean_true(series: pd.Series) -> pd.Series:
    """Return True only for values representing a true flag."""
    text = (
        series.astype("string")
        .fillna("")
        .str.strip()
        .str.lower()
    )
    return text.isin(["true", "1", "yes"])


def value_counts(series: pd.Series) -> dict:
    return {
        str(key): int(value)
        for key, value in series.value_counts(
            dropna=False
        ).items()
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
        dtype="string",
        low_memory=False,
    )

    affected = clinics[
        clinics["spatial_exclusion_reason"]
        == "invalid_or_missing_coordinates"
    ].copy()

    affected_keys = set(
        affected["clinic_key"]
    )
    affected_reviews = reviews[
        reviews["clinic_key"].isin(
            affected_keys
        )
    ].copy()

    location_terms = [
        "zip",
        "postal",
        "address",
        "latitude",
        "longitude",
        "place_id",
        "cid",
    ]

    review_location_columns = [
        column
        for column in affected_reviews.columns
        if any(
            term in column.lower()
            for term in location_terms
        )
    ]

    evidence_counts = {}
    evidence_mask = pd.Series(
        False,
        index=affected_reviews.index,
    )

    boolean_evidence_columns = {
        "non_us_postal_code",
        "zip_mismatch_with_unique_title",
    }

    for column in review_location_columns:
        if column in boolean_evidence_columns:
            column_has_evidence = boolean_true(
                affected_reviews[column]
            )
        else:
            column_has_evidence = nonmissing(
                affected_reviews[column]
            )
        evidence_counts[column] = int(
            column_has_evidence.sum()
        )
        evidence_mask |= column_has_evidence

    review_counts = (
        affected_reviews.groupby(
            "clinic_key"
        )
        .size()
        .rename("review_rows")
    )

    clinic_evidence = affected[
        [
            column
            for column in [
                "clinic_key",
                "title",
                "search_location",
                "task_id",
                "scrape_status",
                "total_reviews_scraped",
            ]
            if column in affected.columns
        ]
    ].copy()

    clinic_evidence = clinic_evidence.merge(
        review_counts,
        left_on="clinic_key",
        right_index=True,
        how="left",
        validate="one_to_one",
    )
    clinic_evidence["review_rows"] = (
        clinic_evidence["review_rows"]
        .fillna(0)
        .astype("int64")
    )

    reviews_with_evidence = (
        affected_reviews.loc[
            evidence_mask,
            ["clinic_key"],
        ]
        .drop_duplicates()
    )

    clinic_evidence[
        "review_location_evidence"
    ] = clinic_evidence[
        "clinic_key"
    ].isin(
        reviews_with_evidence[
            "clinic_key"
        ]
    )

    metadata_counts = {}
    for column in [
        "task_id",
        "title",
        "scrape_status",
        "total_reviews_scraped",
    ]:
        if column in affected.columns:
            metadata_counts[column] = int(
                nonmissing(
                    affected[column]
                ).sum()
            )

    summary = {
        "affected_clinic_rows": int(
            len(affected)
        ),
        "affected_review_rows": int(
            len(affected_reviews)
        ),
        "review_location_columns": (
            review_location_columns
        ),
        "review_location_evidence_counts": (
            evidence_counts
        ),
        "review_rows_with_location_evidence": int(
            evidence_mask.sum()
        ),
        "clinics_with_review_location_evidence": int(
            clinic_evidence[
                "review_location_evidence"
            ].sum()
        ),
        "clinics_without_review_location_evidence": int(
            (
                ~clinic_evidence[
                    "review_location_evidence"
                ]
            ).sum()
        ),
        "clinic_metadata_nonmissing_counts": (
            metadata_counts
        ),
        "linkage_method_counts": (
            value_counts(
                affected_reviews[
                    "review_linkage_method"
                ]
            )
            if "review_linkage_method"
            in affected_reviews.columns
            else {}
        ),
        "scrape_status_counts": (
            value_counts(
                affected["scrape_status"]
            )
            if "scrape_status"
            in affected.columns
            else {}
        ),
        "affected_by_search_location": (
            value_counts(
                affected["search_location"]
            )
        ),
        "maximum_reviews_per_clinic": int(
            clinic_evidence[
                "review_rows"
            ].max()
        ),
        "median_reviews_per_clinic": float(
            clinic_evidence[
                "review_rows"
            ].median()
        ),
    }

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    clinic_evidence.to_csv(
        args.output_directory
        / "unlocated_clinic_evidence.csv",
        index=False,
    )

    summary_path = (
        args.output_directory
        / "unlocated_clinic_summary.json"
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
