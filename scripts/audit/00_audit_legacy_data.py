"""Audit legacy clinic and review data before linkage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.identifiers import normalize_name, normalize_zip


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit legacy clinic and review data."
    )
    parser.add_argument(
        "--legacy-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100_000,
    )
    return parser.parse_args()


def safe_normalize_name(value: Any) -> str | None:
    if pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    return normalize_name(text)


def safe_normalize_zip(value: Any) -> str | None:
    if pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    return normalize_zip(value)


def calculate_share(count: int, total: int) -> float | None:
    if total == 0:
        return None

    return count / total


def main() -> None:
    args = parse_arguments()

    clinics_path = args.legacy_dir / "final_merged_time.csv"
    reviews_path = args.legacy_dir / "all_reviews_detailed.csv"

    if not clinics_path.is_file():
        raise FileNotFoundError(clinics_path)

    if not reviews_path.is_file():
        raise FileNotFoundError(reviews_path)

    clinics = pd.read_csv(
        clinics_path,
        low_memory=False,
    )

    clinics["normalized_title"] = clinics["title"].map(
        safe_normalize_name
    )
    clinics["normalized_zip"] = clinics["zip"].map(
        safe_normalize_zip
    )

    clinics["start_date_parsed"] = pd.to_datetime(
        clinics["start_date"],
        errors="coerce",
    )

    clinic_link_rows = clinics.dropna(
        subset=["normalized_title", "normalized_zip"]
    ).copy()

    clinic_key_counts = (
        clinic_link_rows.groupby(
            ["normalized_title", "normalized_zip"],
            dropna=False,
        )
        .size()
        .rename("clinic_count")
        .reset_index()
    )

    unique_clinic_keys = {
        (row.normalized_title, row.normalized_zip)
        for row in clinic_key_counts.itertuples(index=False)
        if row.clinic_count == 1
    }

    ambiguous_clinic_keys = {
        (row.normalized_title, row.normalized_zip)
        for row in clinic_key_counts.itertuples(index=False)
        if row.clinic_count > 1
    }

    review_total = 0
    review_valid_dates = 0
    review_valid_ratings = 0
    review_invalid_ratings = 0
    review_missing_link_fields = 0
    review_unique_matches = 0
    review_ambiguous_matches = 0
    review_unmatched = 0

    review_columns = [
        "shop_title",
        "shop_zip",
        "date",
        "rating",
    ]

    for chunk in pd.read_csv(
        reviews_path,
        usecols=review_columns,
        chunksize=args.chunk_size,
        low_memory=False,
    ):
        review_total += len(chunk)

        normalized_titles = chunk["shop_title"].map(
            safe_normalize_name
        )
        normalized_zips = chunk["shop_zip"].map(
            safe_normalize_zip
        )

        parsed_dates = pd.to_datetime(
            chunk["date"],
            errors="coerce",
        )
        numeric_ratings = pd.to_numeric(
            chunk["rating"],
            errors="coerce",
        )

        review_valid_dates += int(parsed_dates.notna().sum())
        review_valid_ratings += int(numeric_ratings.notna().sum())

        invalid_rating_mask = (
            numeric_ratings.notna()
            & ~numeric_ratings.between(1, 5)
        )
        review_invalid_ratings += int(
            invalid_rating_mask.sum()
        )

        for normalized_title, normalized_zip in zip(
            normalized_titles,
            normalized_zips,
        ):
            if normalized_title is None or normalized_zip is None:
                review_missing_link_fields += 1
                continue

            link_key = (
                normalized_title,
                normalized_zip,
            )

            if link_key in unique_clinic_keys:
                review_unique_matches += 1
            elif link_key in ambiguous_clinic_keys:
                review_ambiguous_matches += 1
            else:
                review_unmatched += 1

    clinic_total = len(clinics)
    valid_start_dates = int(
        clinics["start_date_parsed"].notna().sum()
    )

    summary = {
        "input_files": {
            "clinics": str(clinics_path),
            "reviews": str(reviews_path),
        },
        "clinics": {
            "total_rows": clinic_total,
            "valid_start_date_rows": valid_start_dates,
            "valid_start_date_share": calculate_share(
                valid_start_dates,
                clinic_total,
            ),
            "rows_with_link_fields": len(clinic_link_rows),
            "unique_title_zip_keys": len(unique_clinic_keys),
            "ambiguous_title_zip_keys": len(
                ambiguous_clinic_keys
            ),
            "rows_in_ambiguous_title_zip_groups": int(
                clinic_key_counts.loc[
                    clinic_key_counts["clinic_count"] > 1,
                    "clinic_count",
                ].sum()
            ),
        },
        "reviews": {
            "total_rows": review_total,
            "valid_date_rows": review_valid_dates,
            "valid_date_share": calculate_share(
                review_valid_dates,
                review_total,
            ),
            "valid_rating_rows": review_valid_ratings,
            "valid_rating_share": calculate_share(
                review_valid_ratings,
                review_total,
            ),
            "invalid_rating_rows": review_invalid_ratings,
            "missing_link_field_rows": (
                review_missing_link_fields
            ),
            "unique_match_rows": review_unique_matches,
            "unique_match_share": calculate_share(
                review_unique_matches,
                review_total,
            ),
            "ambiguous_match_rows": (
                review_ambiguous_matches
            ),
            "ambiguous_match_share": calculate_share(
                review_ambiguous_matches,
                review_total,
            ),
            "unmatched_rows": review_unmatched,
            "unmatched_share": calculate_share(
                review_unmatched,
                review_total,
            ),
        },
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
