import pandas as pd
import pytest

from medical_ratings.panel import aggregate_reviews, build_cumulative_panel


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
