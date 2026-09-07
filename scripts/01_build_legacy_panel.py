"""Build the reproducible legacy clinic-year panel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.panel import aggregate_reviews, build_cumulative_panel


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the legacy clinic-year panel."
    )
    parser.add_argument("--clinics", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--history-start-year",
        type=int,
        default=2008,
    )
    parser.add_argument(
        "--analysis-start-year",
        type=int,
        default=2015,
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=2025,
    )
    return parser.parse_args()


def reason_is_eligible(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .str.strip()
        .str.lower()
        .eq("eligible")
        .fillna(False)
    )


def build_legacy_panel(
    clinics: pd.DataFrame,
    reviews: pd.DataFrame,
    *,
    history_start_year: int = 2008,
    analysis_start_year: int = 2015,
    end_year: int = 2025,
) -> tuple[pd.DataFrame, dict[str, int | float]]:
    """Build one panel while retaining spatial eligibility for later filters."""

    if not history_start_year <= analysis_start_year <= end_year:
        raise ValueError(
            "Expected history_start_year <= analysis_start_year <= end_year"
        )

    required_clinic_columns = {
        "clinic_key",
        "entry_date_proxy",
        "analysis_exclusion_reason",
        "spatial_exclusion_reason",
    }
    required_review_columns = {
        "clinic_key",
        "review_date",
        "rating_numeric",
        "analysis_exclusion_reason",
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

    if clinics["clinic_key"].duplicated().any():
        raise ValueError("Clinic keys are not unique")

    clinic_work = clinics.copy()
    review_work = reviews.copy()

    clinic_work["entry_date_parsed"] = pd.to_datetime(
        clinic_work["entry_date_proxy"],
        errors="coerce",
    )
    clinic_work["entry_year"] = (
        clinic_work["entry_date_parsed"].dt.year.astype("Int64")
    )
    review_work["review_date_parsed"] = pd.to_datetime(
        review_work["review_date"],
        errors="coerce",
    )
    review_work["rating_numeric_parsed"] = pd.to_numeric(
        review_work["rating_numeric"],
        errors="coerce",
    )

    clinic_analysis_eligible = reason_is_eligible(
        clinic_work["analysis_exclusion_reason"]
    )
    review_analysis_eligible = reason_is_eligible(
        review_work["analysis_exclusion_reason"]
    )
    clinic_spatial_eligible = reason_is_eligible(
        clinic_work["spatial_exclusion_reason"]
    )

    eligible_clinics = clinic_work.loc[
        clinic_analysis_eligible
    ].copy()
    eligible_missing_entry = eligible_clinics["entry_year"].isna()
    eligible_after_end = eligible_clinics["entry_year"].gt(end_year).fillna(False)

    panel_clinics = eligible_clinics.loc[
        eligible_clinics["entry_year"].notna()
        & eligible_clinics["entry_year"].le(end_year)
    ].copy()

    preferred_clinic_columns = [
        "clinic_key",
        "title",
        "search_location",
        "latitude",
        "longitude",
        "normalized_zip",
        "entry_date_proxy",
        "entry_date_source",
        "entry_year",
        "analysis_exclusion_reason",
        "spatial_exclusion_reason",
        "location_code_status",
        "used_location_code",
    ]
    selected_clinic_columns = [
        column
        for column in preferred_clinic_columns
        if column in panel_clinics.columns
    ]
    panel_clinics = panel_clinics[selected_clinic_columns].copy()
    panel_clinics["spatial_analysis_eligible"] = reason_is_eligible(
        panel_clinics["spatial_exclusion_reason"]
    )

    panel_clinic_keys = set(panel_clinics["clinic_key"])
    eligible_reviews = review_work.loc[
        review_analysis_eligible
    ].copy()
    review_has_panel_clinic = eligible_reviews["clinic_key"].isin(
        panel_clinic_keys
    )
    panel_reviews = eligible_reviews.loc[review_has_panel_clinic].copy()

    invalid_panel_reviews = (
        panel_reviews["clinic_key"].isna()
        | panel_reviews["review_date_parsed"].isna()
        | panel_reviews["rating_numeric_parsed"].isna()
        | ~panel_reviews["rating_numeric_parsed"].between(1, 5)
    )
    if invalid_panel_reviews.any():
        raise ValueError(
            "Eligible panel reviews contain invalid key, date, or rating. "
            f"Affected rows: {int(invalid_panel_reviews.sum())}"
        )

    yearly_reviews = aggregate_reviews(
        panel_reviews,
        date_column="review_date_parsed",
        rating_column="rating_numeric_parsed",
    )

    panel = build_cumulative_panel(
        panel_clinics,
        yearly_reviews,
        start_year=history_start_year,
        analysis_start_year=analysis_start_year,
        end_year=end_year,
    )
    panel["has_new_reviews"] = panel["new_count"].gt(0)
    panel["has_observed_rating"] = panel["cumulative_votes"].gt(0)

    if panel.duplicated(["clinic_key", "year"]).any():
        raise ValueError("Panel contains duplicate clinic-year rows")

    included_review_year = panel_reviews["review_date_parsed"].dt.year
    panel_period_review = included_review_year.between(
        history_start_year,
        end_year,
    )
    analysis_period_review = included_review_year.between(
        analysis_start_year,
        end_year,
    )

    panel_clinic_count = int(panel["clinic_key"].nunique())
    summary: dict[str, int | float] = {
        "input_clinic_rows": int(len(clinics)),
        "input_review_rows": int(len(reviews)),
        "analysis_eligible_clinic_rows": int(clinic_analysis_eligible.sum()),
        "analysis_eligible_review_rows": int(review_analysis_eligible.sum()),
        "eligible_clinics_missing_entry_year": int(
            eligible_missing_entry.sum()
        ),
        "eligible_clinics_entering_after_end_year": int(
            eligible_after_end.sum()
        ),
        "panel_clinic_rows": panel_clinic_count,
        "spatial_eligible_panel_clinics": int(
            panel.loc[
                panel["spatial_analysis_eligible"],
                "clinic_key",
            ].nunique()
        ),
        "panel_rows": int(len(panel)),
        "analysis_period_panel_rows": int(panel["analysis_period"].sum()),
        "spatial_eligible_panel_rows": int(
            panel["spatial_analysis_eligible"].sum()
        ),
        "eligible_reviews_without_panel_clinic": int(
            (~review_has_panel_clinic).sum()
        ),
        "panel_period_review_rows": int(panel_period_review.sum()),
        "analysis_period_review_rows": int(analysis_period_review.sum()),
        "post_end_year_review_rows": int(
            (included_review_year > end_year).sum()
        ),
        "panel_new_review_rows": int(panel["new_count"].sum()),
        "clinic_keys_with_observed_rating": int(
            panel.loc[
                panel["has_observed_rating"],
                "clinic_key",
            ].nunique()
        ),
        "clinic_keys_without_observed_rating": int(
            panel_clinic_count
            - panel.loc[
                panel["has_observed_rating"],
                "clinic_key",
            ].nunique()
        ),
        "history_start_year": int(history_start_year),
        "analysis_start_year": int(analysis_start_year),
        "end_year": int(end_year),
    }

    return panel, summary


def main() -> None:
    args = parse_arguments()

    clinics = pd.read_csv(args.clinics, low_memory=False)
    reviews = pd.read_csv(args.reviews, low_memory=False)

    panel, summary = build_legacy_panel(
        clinics,
        reviews,
        history_start_year=args.history_start_year,
        analysis_start_year=args.analysis_start_year,
        end_year=args.end_year,
    )

    args.output_directory.mkdir(parents=True, exist_ok=True)
    panel.to_csv(
        args.output_directory / "clinic_year_panel.csv",
        index=False,
    )
    summary_path = args.output_directory / "clinic_year_panel_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
