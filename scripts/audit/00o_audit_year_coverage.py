"""Audit review-year and clinic-entry-year coverage before panel construction."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


PRELIMINARY_REASON_COLUMNS = (
    "analysis_exclusion_reason",
    "preliminary_exclusion_reason",
    "location_exclusion_reason",
    "clinic_exclusion_reason",
    "review_exclusion_reason",
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit annual coverage before building the legacy clinic panel."
        )
    )
    parser.add_argument("--clinics", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def find_column(
    frame: pd.DataFrame,
    candidates: tuple[str, ...],
    label: str,
) -> str:
    for column in candidates:
        if column in frame.columns:
            return column
    raise KeyError(
        f"Could not find {label}. Tried: {list(candidates)}"
    )


def eligible_mask(
    frame: pd.DataFrame,
    reason_column: str,
) -> pd.Series:
    return (
        frame[reason_column]
        .astype("string")
        .str.strip()
        .str.lower()
        .eq("eligible")
        .fillna(False)
    )


def annual_counts(
    frame: pd.DataFrame,
    date_column: str,
    clinic_key_column: str,
    preliminary_mask: pd.Series,
    spatial_mask: pd.Series,
    row_label: str,
) -> pd.DataFrame:
    work = frame.loc[
        frame[date_column].notna(),
        [clinic_key_column, date_column],
    ].copy()
    work["year"] = work[date_column].dt.year.astype("int64")
    work["preliminary_eligible"] = preliminary_mask.loc[work.index]
    work["spatial_eligible"] = spatial_mask.loc[work.index]

    total = work.groupby("year").agg(
        **{
            f"{row_label}_rows": (
                clinic_key_column,
                "size",
            ),
            "clinic_keys": (
                clinic_key_column,
                "nunique",
            ),
        }
    )

    preliminary = (
        work.loc[work["preliminary_eligible"]]
        .groupby("year")
        .agg(
            **{
                f"preliminary_eligible_{row_label}_rows": (
                    clinic_key_column,
                    "size",
                ),
                "preliminary_eligible_clinic_keys": (
                    clinic_key_column,
                    "nunique",
                ),
            }
        )
    )

    spatial = (
        work.loc[work["spatial_eligible"]]
        .groupby("year")
        .agg(
            **{
                f"spatial_eligible_{row_label}_rows": (
                    clinic_key_column,
                    "size",
                ),
                "spatial_eligible_clinic_keys": (
                    clinic_key_column,
                    "nunique",
                ),
            }
        )
    )

    return (
        total.join(preliminary, how="outer")
        .join(spatial, how="outer")
        .fillna(0)
        .astype("int64")
        .reset_index()
        .sort_values("year")
    )


def date_summary(
    dates: pd.Series,
    preliminary_mask: pd.Series,
    spatial_mask: pd.Series,
) -> dict[str, int | float | None]:
    valid = dates.notna()
    years = dates.loc[valid].dt.year
    current_year = datetime.now().year

    return {
        "total_rows": int(len(dates)),
        "valid_date_rows": int(valid.sum()),
        "invalid_or_missing_date_rows": int((~valid).sum()),
        "valid_date_share": (
            float(valid.mean()) if len(dates) else None
        ),
        "minimum_year": (
            int(years.min()) if not years.empty else None
        ),
        "maximum_year": (
            int(years.max()) if not years.empty else None
        ),
        "distinct_years": int(years.nunique()),
        "future_date_rows": int(
            (dates.loc[valid].dt.year > current_year).sum()
        ),
        "preliminary_eligible_valid_date_rows": int(
            (valid & preliminary_mask).sum()
        ),
        "spatial_eligible_valid_date_rows": int(
            (valid & spatial_mask).sum()
        ),
    }


def main() -> None:
    args = parse_arguments()

    clinics = pd.read_csv(args.clinics, low_memory=False)
    reviews = pd.read_csv(args.reviews, low_memory=False)

    required_clinic_columns = {
        "clinic_key",
        "entry_date_proxy",
        "spatial_exclusion_reason",
    }
    required_review_columns = {
        "clinic_key",
        "spatial_exclusion_reason",
    }

    missing_clinic_columns = required_clinic_columns - set(clinics.columns)
    missing_review_columns = required_review_columns - set(reviews.columns)

    if missing_clinic_columns:
        raise KeyError(
            "Missing clinic columns: "
            f"{sorted(missing_clinic_columns)}"
        )
    if missing_review_columns:
        raise KeyError(
            "Missing review columns: "
            f"{sorted(missing_review_columns)}"
        )

    review_date_column = find_column(
        reviews,
        ("review_date", "date"),
        "review date column",
    )
    clinic_preliminary_reason = find_column(
        clinics,
        PRELIMINARY_REASON_COLUMNS,
        "clinic preliminary exclusion reason",
    )
    review_preliminary_reason = find_column(
        reviews,
        PRELIMINARY_REASON_COLUMNS,
        "review preliminary exclusion reason",
    )

    clinics["entry_date_parsed"] = pd.to_datetime(
        clinics["entry_date_proxy"],
        errors="coerce",
    )
    reviews["review_date_parsed"] = pd.to_datetime(
        reviews[review_date_column],
        errors="coerce",
    )

    clinic_preliminary = eligible_mask(
        clinics,
        clinic_preliminary_reason,
    )
    review_preliminary = eligible_mask(
        reviews,
        review_preliminary_reason,
    )
    clinic_spatial = eligible_mask(
        clinics,
        "spatial_exclusion_reason",
    )
    review_spatial = eligible_mask(
        reviews,
        "spatial_exclusion_reason",
    )

    review_year_counts = annual_counts(
        reviews,
        "review_date_parsed",
        "clinic_key",
        review_preliminary,
        review_spatial,
        "review",
    )
    entry_year_counts = annual_counts(
        clinics,
        "entry_date_parsed",
        "clinic_key",
        clinic_preliminary,
        clinic_spatial,
        "clinic",
    )

    summary = {
        "clinic_preliminary_reason_column": clinic_preliminary_reason,
        "review_preliminary_reason_column": review_preliminary_reason,
        "review_source_date_column": review_date_column,
        "review_dates": date_summary(
            reviews["review_date_parsed"],
            review_preliminary,
            review_spatial,
        ),
        "clinic_entry_dates": date_summary(
            clinics["entry_date_parsed"],
            clinic_preliminary,
            clinic_spatial,
        ),
    }

    args.output_directory.mkdir(parents=True, exist_ok=True)

    review_year_counts.to_csv(
        args.output_directory / "review_year_counts.csv",
        index=False,
    )
    entry_year_counts.to_csv(
        args.output_directory / "entry_year_counts.csv",
        index=False,
    )

    summary_path = args.output_directory / "year_coverage_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
