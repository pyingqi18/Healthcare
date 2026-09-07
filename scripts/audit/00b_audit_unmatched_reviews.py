"""Audit unmatched legacy review keys."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.identifiers import normalize_name, normalize_zip


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


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit unmatched legacy review keys."
    )
    parser.add_argument(
        "--legacy-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output-directory",
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

    clinics_path = args.legacy_dir / "final_merged_time.csv"
    reviews_path = args.legacy_dir / "all_reviews_detailed.csv"

    clinics = pd.read_csv(
        clinics_path,
        usecols=["title", "zip"],
        low_memory=False,
    )

    clinics["normalized_title"] = clinics["title"].map(
        safe_normalize_name
    )
    clinics["normalized_zip"] = clinics["zip"].map(
        safe_normalize_zip
    )

    clinic_rows = clinics.dropna(
        subset=["normalized_title", "normalized_zip"]
    )

    clinic_keys = set(
        zip(
            clinic_rows["normalized_title"],
            clinic_rows["normalized_zip"],
        )
    )

    clinic_names = set(clinic_rows["normalized_title"])
    clinic_zips = set(clinic_rows["normalized_zip"])

    unmatched_counter: Counter[tuple[str, str]] = Counter()
    review_total_rows = 0
    review_linkable_rows = 0
    review_matched_rows = 0
    review_missing_link_field_rows = 0

    for chunk in pd.read_csv(
        reviews_path,
        usecols=["shop_title", "shop_zip"],
        chunksize=args.chunk_size,
        low_memory=False,
    ):
        review_total_rows += len(chunk)
        normalized_titles = chunk["shop_title"].map(
            safe_normalize_name
        )
        normalized_zips = chunk["shop_zip"].map(
            safe_normalize_zip
        )

        for title, zip_code in zip(
            normalized_titles,
            normalized_zips,
        ):
            if (
                title is None
                or zip_code is None
                or pd.isna(title)
                or pd.isna(zip_code)
            ):
                review_missing_link_field_rows += 1
                continue

            review_linkable_rows += 1

            key = (title, zip_code)

            if key not in clinic_keys:
                unmatched_counter[key] += 1
            else:
                review_matched_rows += 1

    records = []

    for (title, zip_code), review_count in (
        unmatched_counter.items()
    ):
        name_exists = title in clinic_names
        zip_exists = zip_code in clinic_zips

        if name_exists and not zip_exists:
            classification = "name_exists_with_different_zip"
        elif zip_exists and not name_exists:
            classification = "zip_exists_with_different_name"
        elif name_exists and zip_exists:
            classification = "name_and_zip_exist_separately"
        else:
            classification = "neither_name_nor_zip_exists"

        records.append(
            {
                "normalized_shop_title": title,
                "normalized_shop_zip": zip_code,
                "review_count": review_count,
                "name_exists_in_clinics": name_exists,
                "zip_exists_in_clinics": zip_exists,
                "classification": classification,
            }
        )

    unmatched_columns = [
        "normalized_shop_title",
        "normalized_shop_zip",
        "review_count",
        "name_exists_in_clinics",
        "zip_exists_in_clinics",
        "classification",
    ]

    unmatched = pd.DataFrame.from_records(
        records,
        columns=unmatched_columns,
    )

    if not unmatched.empty:
        unmatched = unmatched.sort_values(
            "review_count",
            ascending=False,
        ).reset_index(drop=True)

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    unmatched_path = (
        args.output_directory
        / "unmatched_review_keys.csv"
    )

    unmatched.to_csv(
        unmatched_path,
        index=False,
    )

    total_unmatched_reviews = int(
        unmatched["review_count"].sum()
    )

    def top_share(number_of_keys: int) -> float | None:
        if total_unmatched_reviews == 0:
            return None

        return float(
            unmatched.head(number_of_keys)[
                "review_count"
            ].sum()
            / total_unmatched_reviews
        )

    if unmatched.empty:
        classification_by_key = {}
        classification_by_review = {}
    else:
        classification_by_key = {
            str(key): int(value)
            for key, value in unmatched[
                "classification"
            ].value_counts().items()
        }

        classification_by_review = {
            str(key): int(value)
            for key, value in unmatched.groupby(
                "classification"
            )["review_count"].sum().items()
        }

    summary = {
        "total_review_rows": review_total_rows,
        "linkable_review_rows": review_linkable_rows,
        "matched_review_rows": review_matched_rows,
        "missing_link_field_rows": (
            review_missing_link_field_rows
        ),
        "total_unmatched_reviews": total_unmatched_reviews,
        "matched_share_of_all_reviews": (
            review_matched_rows / review_total_rows
            if review_total_rows > 0
            else None
        ),
        "missing_link_field_share": (
            review_missing_link_field_rows / review_total_rows
            if review_total_rows > 0
            else None
        ),
        "unmatched_share_of_all_reviews": (
            total_unmatched_reviews / review_total_rows
            if review_total_rows > 0
            else None
        ),
        "unmatched_share_of_linkable_reviews": (
            total_unmatched_reviews / review_linkable_rows
            if review_linkable_rows > 0
            else None
        ),
        "distinct_unmatched_title_zip_keys": len(unmatched),
        "top_10_key_share": top_share(10),
        "top_50_key_share": top_share(50),
        "top_100_key_share": top_share(100),
        "maximum_reviews_for_one_unmatched_key": (
            int(unmatched["review_count"].max())
            if not unmatched.empty
            else 0
        ),
        "median_reviews_per_unmatched_key": (
            float(unmatched["review_count"].median())
            if not unmatched.empty
            else 0
        ),
        "classification_by_distinct_key": (
            classification_by_key
        ),
        "classification_by_review_count": (
            classification_by_review
        ),
    }

    summary_path = (
        args.output_directory
        / "unmatched_review_summary.json"
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