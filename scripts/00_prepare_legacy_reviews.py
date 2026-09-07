"""Prepare legacy reviews and link them to clinic identities."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from medical_ratings.legacy import (
    prepare_legacy_reviews,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare legacy review data."
    )
    parser.add_argument(
        "--reviews",
        type=Path,
        required=True,
    )
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
    parser.add_argument(
        "--summary",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100_000,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    if args.reviews.resolve() == args.output.resolve():
        raise ValueError(
            "Output path cannot overwrite raw reviews"
        )

    clinics = pd.read_csv(
        args.clinics,
        low_memory=False,
        dtype={
            "zip": "string",
            "normalized_zip": "string",
            "title_zip_key": "string",
            "clinic_key": "string",
        },
    )

    if clinics["clinic_key"].isna().any():
        raise ValueError(
            "Prepared clinics contain missing clinic_key"
        )

    if clinics["clinic_key"].duplicated().any():
        raise ValueError(
            "Prepared clinics contain duplicate clinic_key"
        )

    valid_clinic_keys = set(
        clinics["clinic_key"]
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.summary.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    linkage_counts: Counter[str] = Counter()

    total_input_rows = 0
    total_output_rows = 0
    matched_rows = 0
    unmatched_rows = 0
    valid_date_rows = 0
    invalid_date_rows = 0
    valid_rating_rows = 0
    missing_or_invalid_rating_rows = 0
    out_of_range_rating_rows = 0
    non_us_postal_rows = 0
    non_us_postal_matched_rows = 0
    clinic_keys_with_reviews: set[str] = set()

    first_chunk = True

    for chunk in pd.read_csv(
        args.reviews,
        chunksize=args.chunk_size,
        low_memory=False,
        dtype={
            "shop_title": "string",
            "shop_zip": "string",
        },
    ):
        total_input_rows += len(chunk)

        prepared = prepare_legacy_reviews(
            chunk,
            clinics,
        )

        total_output_rows += len(prepared)

        unknown_keys = set(
            prepared["clinic_key"].dropna()
        ) - valid_clinic_keys

        if unknown_keys:
            raise ValueError(
                "Reviews contain clinic_key values "
                "not found in the clinic table"
            )

        linkage_counts.update(
            prepared[
                "review_linkage_method"
            ].value_counts(
                dropna=False
            ).to_dict()
        )

        matched = (
            prepared["review_linkage_status"]
            == "matched"
        )

        matched_rows += int(matched.sum())
        unmatched_rows += int((~matched).sum())

        valid_dates = prepared["review_date"].notna()
        valid_date_rows += int(valid_dates.sum())
        invalid_date_rows += int(
            (~valid_dates).sum()
        )

        numeric_rating = prepared["rating_numeric"]

        valid_rating = (
            numeric_rating.notna()
            & numeric_rating.between(1, 5)
        )

        valid_rating_rows += int(
            valid_rating.sum()
        )

        missing_or_invalid_rating_rows += int(
            numeric_rating.isna().sum()
        )

        out_of_range_rating_rows += int(
            (
                numeric_rating.notna()
                & ~numeric_rating.between(1, 5)
            ).sum()
        )

        non_us = prepared["non_us_postal_code"]

        non_us_postal_rows += int(
            non_us.sum()
        )

        non_us_postal_matched_rows += int(
            (non_us & matched).sum()
        )

        clinic_keys_with_reviews.update(
            prepared.loc[
                matched,
                "clinic_key",
            ].dropna()
        )

        prepared.to_csv(
            args.output,
            mode="w" if first_chunk else "a",
            header=first_chunk,
            index=False,
        )

        first_chunk = False

    if first_chunk:
        raise ValueError(
            "No review rows were read"
        )

    if total_input_rows != total_output_rows:
        raise ValueError(
            "Review row count changed during preparation. "
            f"Input rows: {total_input_rows}. "
            f"Output rows: {total_output_rows}."
        )

    if matched_rows + unmatched_rows != total_output_rows:
        raise ValueError(
            "Matched and unmatched counts "
            "do not equal total rows"
        )

    linkage_methods = [
        "title_zip",
        "missing_zip_unique_title",
        "non_us_postal_unique_title",
        "zip_mismatch_unique_title",
        "unmatched_title_zip",
        "missing_zip_ambiguous_title",
        "missing_zip_no_title_match",
        "missing_title",
    ]


    summary = {
        "input_review_rows": total_input_rows,
        "output_review_rows": total_output_rows,
        "matched_review_rows": matched_rows,
        "unmatched_review_rows": unmatched_rows,
        "matched_review_share": (
            matched_rows / total_output_rows
            if total_output_rows
            else None
        ),
        "linkage_method_counts": {
            method: int(
                linkage_counts.get(method, 0)
            )
            for method in linkage_methods
        },
        "valid_review_date_rows": valid_date_rows,
        "invalid_review_date_rows": (
            invalid_date_rows
        ),
        "valid_rating_rows": valid_rating_rows,
        "missing_or_invalid_rating_rows": (
            missing_or_invalid_rating_rows
        ),
        "out_of_range_rating_rows": (
            out_of_range_rating_rows
        ),
        "non_us_postal_rows": (
            non_us_postal_rows
        ),
        "non_us_postal_matched_rows": (
            non_us_postal_matched_rows
        ),
        "clinic_keys_with_reviews": len(
            clinic_keys_with_reviews
        ),
        "clinic_keys_without_reviews": (
            len(valid_clinic_keys)
            - len(clinic_keys_with_reviews)
        ),
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