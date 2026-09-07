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
    start_year: int | None = None,
    analysis_start_year: int | None = None,
    allow_missing_entry_year: bool = False,
) -> pd.DataFrame:
    """Create a clinic-year panel and cumulative rating outcomes.

    Cumulative outcomes are calculated before ``start_year`` is applied, so
    reviews from earlier years remain in the opening cumulative balance.
    """

    required = [clinic_key, entry_year_column]
    missing = [column for column in required if column not in clinics.columns]
    if missing:
        raise KeyError(f"Missing clinic columns: {missing}")

    required_yearly = [
        clinic_key,
        "year",
        "new_count",
        "new_stars",
        "low_review_count",
    ]
    missing_yearly = [
        column
        for column in required_yearly
        if column not in yearly_reviews.columns
    ]
    if missing_yearly:
        raise KeyError(
            f"Missing yearly review columns: {missing_yearly}"
        )

    if start_year is not None and start_year > end_year:
        raise ValueError("start_year cannot be later than end_year")

    if (
        analysis_start_year is not None
        and analysis_start_year > end_year
    ):
        raise ValueError(
            "analysis_start_year cannot be later than end_year"
        )

    clinic_data = clinics.copy()
    clinic_data[entry_year_column] = pd.to_numeric(
        clinic_data[entry_year_column], errors="coerce"
    ).astype("Int64")

    missing_entry_year = (
        clinic_data[clinic_key].notna()
        & clinic_data[entry_year_column].isna()
    )
    if missing_entry_year.any() and not allow_missing_entry_year:
        raise ValueError(
            "Clinics contain missing entry years. "
            "Filter them explicitly or set "
            "allow_missing_entry_year=True. "
            f"Affected rows: {int(missing_entry_year.sum())}"
        )

    clinic_data = clinic_data.dropna(subset=[clinic_key, entry_year_column])
    assert_unique(clinic_data, [clinic_key], label="Clinic identity table")

    yearly_data = yearly_reviews.copy()
    yearly_data["year"] = pd.to_numeric(
        yearly_data["year"],
        errors="coerce",
    ).astype("Int64")
    if yearly_data["year"].isna().any():
        raise ValueError("Yearly reviews contain missing or invalid years")
    yearly_data["year"] = yearly_data["year"].astype("int64")
    assert_unique(
        yearly_data,
        [clinic_key, "year"],
        label="Review-year panel",
    )

    known_clinic_keys = set(clinic_data[clinic_key])
    unknown_review_keys = (
        yearly_data[clinic_key].notna()
        & ~yearly_data[clinic_key].isin(known_clinic_keys)
    )
    if unknown_review_keys.any():
        raise ValueError(
            "Yearly reviews contain clinic keys absent from the clinic table. "
            f"Affected rows: {int(unknown_review_keys.sum())}"
        )

    entry_year_map = clinic_data.set_index(clinic_key)[entry_year_column]
    review_entry_year = yearly_data[clinic_key].map(entry_year_map)
    review_before_entry = yearly_data["year"] < review_entry_year
    if review_before_entry.any():
        raise ValueError(
            "Yearly reviews occur before the corresponding clinic entry year. "
            f"Affected rows: {int(review_before_entry.sum())}"
        )

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
    panel = panel.merge(yearly_data, on=[clinic_key, "year"], how="left")
    for column in ["new_count", "new_stars", "low_review_count"]:
        panel[column] = pd.to_numeric(panel[column], errors="coerce").fillna(0)

    panel["new_count"] = panel["new_count"].astype("int64")
    panel["low_review_count"] = panel["low_review_count"].astype("int64")

    panel["annual_rating"] = np.where(
        panel["new_count"] > 0,
        panel["new_stars"] / panel["new_count"],
        np.nan,
    )
    panel["annual_low_review_share"] = np.where(
        panel["new_count"] > 0,
        panel["low_review_count"] / panel["new_count"],
        np.nan,
    )

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

    if start_year is not None:
        panel = panel.loc[panel["year"] >= start_year].copy()

    if analysis_start_year is not None:
        panel["analysis_period"] = panel["year"].between(
            analysis_start_year,
            end_year,
        )

    assert_unique(panel, [clinic_key, "year"], label="Cumulative clinic-year panel")
    return panel
