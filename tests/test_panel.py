import pandas as pd

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
