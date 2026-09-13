import pandas as pd
import pytest

from medical_ratings.panel import (
    aggregate_reviews,
    build_cumulative_panel,
    parse_mixed_datetime,
)


def test_panel_construction() -> None:
    clinics = pd.DataFrame(
        {"clinic_key": ["a"], "entry_year": [2020], "mapped_location": ["market"]}
    )
    reviews = pd.DataFrame(
        {
            "clinic_key": ["a", "a"],
            "review_date": ["2020-01-01", "2021-01-01"],
            "rating": [5, 3],
        }
    )
    yearly = aggregate_reviews(reviews)
    panel = build_cumulative_panel(clinics, yearly, end_year=2022)
    assert panel["year"].tolist() == [2020, 2021, 2022]
    assert panel["dynamic_rating"].tolist() == [5.0, 4.0, 4.0]
    assert panel["cumulative_votes"].tolist() == [1, 2, 2]


def test_panel_preserves_reviews_before_output_start_year() -> None:
    clinics = pd.DataFrame(
        {
            "clinic_key": ["a"],
            "entry_year": [2014],
            "mapped_location": ["market"],
        }
    )
    yearly = pd.DataFrame(
        {
            "clinic_key": ["a", "a"],
            "year": [2014, 2015],
            "new_count": [2, 1],
            "new_stars": [10, 3],
            "low_review_count": [0, 1],
        }
    )

    panel = build_cumulative_panel(
        clinics,
        yearly,
        start_year=2015,
        analysis_start_year=2015,
        end_year=2016,
    )

    assert panel["year"].tolist() == [2015, 2016]
    assert panel["cumulative_votes"].tolist() == [3, 3]
    assert panel["dynamic_rating"].tolist() == pytest.approx(
        [13 / 3, 13 / 3]
    )
    assert panel["analysis_period"].all()


def test_panel_rejects_implicit_missing_entry_year_loss() -> None:
    clinics = pd.DataFrame(
        {
            "clinic_key": ["a"],
            "entry_year": [pd.NA],
        }
    )
    yearly = pd.DataFrame(
        columns=[
            "clinic_key",
            "year",
            "new_count",
            "new_stars",
            "low_review_count",
        ]
    )

    with pytest.raises(
        ValueError,
        match="missing entry years",
    ):
        build_cumulative_panel(
            clinics,
            yearly,
            end_year=2025,
        )


def test_mixed_legacy_and_utc_review_dates_are_preserved() -> None:
    values = pd.Series(
        [
            "2020-01-01",
            "2025-06-01 12:30:00",
            "2026-09-07 00:13:51 +00:00",
            "2026-09-07T00:13:51Z",
        ]
    )

    parsed = parse_mixed_datetime(values)

    assert parsed.notna().all()
    assert parsed.dt.year.tolist() == [2020, 2025, 2026, 2026]
    assert parsed.dt.tz is None

    reviews = pd.DataFrame(
        {
            "clinic_key": ["a", "a", "a", "a"],
            "review_date": values,
            "rating": [5, 4, 3, 2],
        }
    )
    yearly = aggregate_reviews(reviews)
    assert int(yearly["new_count"].sum()) == 4
    assert yearly["year"].tolist() == [2020, 2025, 2026]
