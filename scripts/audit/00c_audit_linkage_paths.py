"""Audit all available legacy review linkage paths."""

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
        description="Audit legacy review linkage paths."
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

    clinic_title_counts = Counter(
        title
        for title in clinics["normalized_title"]
        if title is not None and not pd.isna(title)
    )

    clinic_pair_counts = Counter(
        (title, zip_code)
        for title, zip_code in zip(
            clinics["normalized_title"],
            clinics["normalized_zip"],
        )
        if (
            title is not None
            and zip_code is not None
            and not pd.isna(title)
            and not pd.isna(zip_code)
        )
    )

    category_counts: Counter[str] = Counter()
    missing_zip_title_counts: Counter[str] = Counter()

    total_review_rows = 0

    for chunk in pd.read_csv(
        reviews_path,
        usecols=["shop_title", "shop_zip"],
        chunksize=args.chunk_size,
        low_memory=False,
    ):
        total_review_rows += len(chunk)

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
            if title is None or pd.isna(title):
                category_counts["missing_title"] += 1
                continue

            if zip_code is None or pd.isna(zip_code):
                missing_zip_title_counts[title] += 1

                title_match_count = clinic_title_counts.get(
                    title,
                    0,
                )

                if title_match_count == 1:
                    category_counts[
                        "missing_zip_unique_name_match"
                    ] += 1
                elif title_match_count > 1:
                    category_counts[
                        "missing_zip_ambiguous_name_match"
                    ] += 1
                else:
                    category_counts[
                        "missing_zip_no_name_match"
                    ] += 1

                continue

            pair_match_count = clinic_pair_counts.get(
                (title, zip_code),
                0,
            )

            if pair_match_count == 1:
                category_counts[
                    "unique_title_zip_match"
                ] += 1
            elif pair_match_count > 1:
                category_counts[
                    "ambiguous_title_zip_match"
                ] += 1
            else:
                category_counts[
                    "unmatched_title_zip"
                ] += 1

    missing_zip_records = []

    for title, review_count in missing_zip_title_counts.items():
        clinic_title_match_count = clinic_title_counts.get(
            title,
            0,
        )

        if clinic_title_match_count == 1:
            classification = "unique_name_match"
        elif clinic_title_match_count > 1:
            classification = "ambiguous_name_match"
        else:
            classification = "no_name_match"

        missing_zip_records.append(
            {
                "normalized_shop_title": title,
                "review_count": review_count,
                "clinic_title_match_count": (
                    clinic_title_match_count
                ),
                "classification": classification,
            }
        )

    missing_zip_columns = [
        "normalized_shop_title",
        "review_count",
        "clinic_title_match_count",
        "classification",
    ]

    missing_zip_report = pd.DataFrame.from_records(
        missing_zip_records,
        columns=missing_zip_columns,
    )

    if not missing_zip_report.empty:
        missing_zip_report = missing_zip_report.sort_values(
            "review_count",
            ascending=False,
        ).reset_index(drop=True)

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    missing_zip_report.to_csv(
        args.output_directory
        / "missing_zip_review_titles.csv",
        index=False,
    )

    ordered_categories = [
        "unique_title_zip_match",
        "ambiguous_title_zip_match",
        "unmatched_title_zip",
        "missing_zip_unique_name_match",
        "missing_zip_ambiguous_name_match",
        "missing_zip_no_name_match",
        "missing_title",
    ]

    counts = {
        category: int(category_counts.get(category, 0))
        for category in ordered_categories
    }

    shares = {
        category: (
            count / total_review_rows
            if total_review_rows > 0
            else None
        )
        for category, count in counts.items()
    }

    accounted_rows = sum(counts.values())

    summary = {
        "total_review_rows": total_review_rows,
        "accounted_review_rows": accounted_rows,
        "all_rows_accounted_for": (
            accounted_rows == total_review_rows
        ),
        "category_counts": counts,
        "category_shares": shares,
        "distinct_missing_zip_titles": len(
            missing_zip_report
        ),
        "clinic_title_zip_keys": len(
            clinic_pair_counts
        ),
        "ambiguous_clinic_title_zip_keys": int(
            sum(
                count > 1
                for count in clinic_pair_counts.values()
            )
        ),
        "ambiguous_clinic_titles": int(
            sum(
                count > 1
                for count in clinic_title_counts.values()
            )
        ),
    }

    summary_path = (
        args.output_directory
        / "linkage_path_summary.json"
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