"""Review-year panel construction."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .validation import assert_unique


def aggregate_reviews(
    reviews: pd.DataFrame,
    *,
    clinic_key: str = "clinic_key",
    date_column: str = "review_date",
    rating_column: str = "rating",
    low_rating_threshold: float = 3.0,
) -> pd.DataFrame:
    """Aggregate review-level records to clinic-year outcomes."""

    required = [clinic_key, date_column, rating_column]
    missing = [column for column in required if column not in reviews.columns]
    if missing:
        raise KeyError(f"Missing review columns: {missing}")

    data = reviews[required].copy()
    data[date_column] = pd.to_datetime(data[date_column], errors="coerce")
    data[rating_column] = pd.to_numeric(data[rating_column], errors="coerce")
    data = data.dropna(subset=required)
    data["year"] = data[date_column].dt.year.astype(int)
    data["is_low_review"] = (data[rating_column] <= low_rating_threshold).astype(int)

    yearly = (
        data.groupby([clinic_key, "year"], as_index=False)
        .agg(
            new_count=(rating_column, "count"),
            new_stars=(rating_column, "sum"),
            low_review_count=("is_low_review", "sum"),
        )
        .sort_values([clinic_key, "year"])
    )
    assert_unique(yearly, [clinic_key, "year"], label="Review-year panel")
    return yearly


def build_cumulative_panel(
    clinics: pd.DataFrame,
    yearly_reviews: pd.DataFrame,
    *,
    end_year: int,
    clinic_key: str = "clinic_key",
    entry_year_column: str = "entry_year",
) -> pd.DataFrame:
    """Create a clinic-year panel and cumulative rating outcomes."""

    required = [clinic_key, entry_year_column]
    missing = [column for column in required if column not in clinics.columns]
    if missing:
        raise KeyError(f"Missing clinic columns: {missing}")

    clinic_data = clinics.copy()
    clinic_data[entry_year_column] = pd.to_numeric(
        clinic_data[entry_year_column], errors="coerce"
    ).astype("Int64")
    clinic_data = clinic_data.dropna(subset=[clinic_key, entry_year_column])
    assert_unique(clinic_data, [clinic_key], label="Clinic identity table")

    frames: list[pd.DataFrame] = []
    for _, clinic in clinic_data.iterrows():
        entry_year = int(clinic[entry_year_column])
        if entry_year > end_year:
            continue
        years = pd.DataFrame({"year": range(entry_year, end_year + 1)})
        for column, value in clinic.items():
            years[column] = value
        frames.append(years)

    if not frames:
        return pd.DataFrame()

    panel = pd.concat(frames, ignore_index=True)
    panel = panel.merge(yearly_reviews, on=[clinic_key, "year"], how="left")
    for column in ["new_count", "new_stars", "low_review_count"]:
        panel[column] = pd.to_numeric(panel[column], errors="coerce").fillna(0)

    panel = panel.sort_values([clinic_key, "year"])
    grouped = panel.groupby(clinic_key, sort=False)
    panel["cumulative_votes"] = grouped["new_count"].cumsum()
    panel["cumulative_stars"] = grouped["new_stars"].cumsum()
    panel["cumulative_low_reviews"] = grouped["low_review_count"].cumsum()
    panel["dynamic_rating"] = np.where(
        panel["cumulative_votes"] > 0,
        panel["cumulative_stars"] / panel["cumulative_votes"],
        np.nan,
    )
    panel["cumulative_low_review_share"] = np.where(
        panel["cumulative_votes"] > 0,
        panel["cumulative_low_reviews"] / panel["cumulative_votes"],
        np.nan,
    )
    panel["log_votes_dynamic"] = np.log1p(panel["cumulative_votes"])
    panel["clinic_age"] = panel["year"] - panel[entry_year_column].astype(int)
    assert_unique(panel, [clinic_key, "year"], label="Cumulative clinic-year panel")
    return panel
