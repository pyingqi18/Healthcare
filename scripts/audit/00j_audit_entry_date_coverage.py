"""Audit entry-date coverage using safe title and ZIP matches."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from medical_ratings.identifiers import (
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
        "--output",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def add_key(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()

    result["normalized_title"] = (
        result["title"].map(normalize_name)
    )
    result["normalized_zip"] = (
        result["zip"].map(normalize_zip)
    )

    complete = (
        result["normalized_title"].notna()
        & result["normalized_zip"].notna()
    )

    result["title_zip_key"] = pd.Series(
        pd.NA,
        index=result.index,
        dtype="string",
    )

    result.loc[complete, "title_zip_key"] = (
        result.loc[complete, "normalized_title"]
        + "|"
        + result.loc[complete, "normalized_zip"]
    )

    return result


def main() -> None:
    args = parse_arguments()

    clinics = add_key(
        pd.read_csv(
            args.clinics,
            low_memory=False,
        )
    )

    timeline = add_key(
        pd.read_csv(
            args.timeline,
            low_memory=False,
        )
    )

    safe_timeline = timeline.dropna(
        subset=["title_zip_key"]
    ).copy()

    if safe_timeline["title_zip_key"].duplicated().any():
        raise ValueError(
            "Timeline contains duplicate complete title and ZIP keys"
        )

    website_year_map = safe_timeline.set_index(
        "title_zip_key"
    )["est_founded"]

    clinics["website_founded_year"] = (
        clinics["title_zip_key"].map(
            website_year_map
        )
    )
    matched_title_zip = (
        clinics["title_zip_key"]
        .isin(safe_timeline["title_zip_key"])
    )

    website_year = pd.to_numeric(
        clinics["website_founded_year"],
        errors="coerce",
    )

    current_year = datetime.now().year

    valid_website_year = website_year.between(
        1800,
        current_year,
    )

    website_date = pd.to_datetime(
        website_year.where(valid_website_year)
        .astype("Int64")
        .astype("string")
        + "-12-31",
        errors="coerce",
    )

    review_date = pd.to_datetime(
        clinics["earliest_review_date"],
        errors="coerce",
    )

    has_website = website_date.notna()
    has_review = review_date.notna()
    has_either = has_website | has_review
    has_both = has_website & has_review

    website_earlier = (
        has_both
        & (website_date < review_date)
    )

    review_earlier_or_equal = (
        has_both
        & (review_date <= website_date)
    )

    summary = {
        "premerge_clinic_rows": len(clinics),
        "safe_title_zip_matches": int(
            matched_title_zip.sum()
        ),
        "matched_nonmissing_est_founded": int(
            clinics["website_founded_year"]
            .notna()
            .sum()
        ),
        "valid_website_dates": int(
            has_website.sum()
        ),
        "valid_earliest_review_dates": int(
            has_review.sum()
        ),
        "both_dates_available": int(
            has_both.sum()
        ),
        "website_date_only": int(
            (has_website & ~has_review).sum()
        ),
        "review_date_only": int(
            (has_review & ~has_website).sum()
        ),
        "website_date_earlier": int(
            website_earlier.sum()
        ),
        "review_date_earlier_or_equal": int(
            review_earlier_or_equal.sum()
        ),
        "combined_valid_entry_dates": int(
            has_either.sum()
        ),
        "combined_missing_entry_dates": int(
            (~has_either).sum()
        ),
        "combined_entry_date_coverage": (
            float(has_either.mean())
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