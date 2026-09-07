import pandas as pd
import pytest

from medical_ratings.legacy import (
    prepare_legacy_clinics,
)


def test_prepare_legacy_clinics_uses_safe_match() -> None:
    clinics = pd.DataFrame(
        {
            "title": ["Clinic A", "Clinic B"],
            "zip": [7087.0, None],
            "address": ["1 Main St", "2 Main St"],
            "latitude": [40.0, 41.0],
            "longitude": [-74.0, -75.0],
            "earliest_review_date": [
                "2020-01-01",
                "2019-01-01",
            ],
        }
    )

    timeline = pd.DataFrame(
        {
            "title": ["Clinic A", "Clinic B"],
            "zip": ["07087", None],
            "est_founded": [2010, 2000],
        }
    )

    result = prepare_legacy_clinics(
        clinics,
        timeline,
        current_year=2026,
    )

    assert len(result) == 2

    assert (
        result.loc[0, "timeline_match_method"]
        == "title_zip"
    )
    assert (
        result.loc[0, "website_founded_year"]
        == 2010
    )
    assert (
        result.loc[0, "entry_date_proxy"]
        == pd.Timestamp("2010-12-31")
    )
    assert (
        result.loc[0, "entry_date_source"]
        == "website"
    )

    assert (
        result.loc[1, "timeline_match_method"]
        == "unmatched"
    )
    assert pd.isna(
        result.loc[1, "website_founded_year"]
    )
    assert (
        result.loc[1, "entry_date_proxy"]
        == pd.Timestamp("2019-01-01")
    )
    assert (
        result.loc[1, "entry_date_source"]
        == "first_review"
    )


def test_duplicate_timeline_keys_are_rejected() -> None:
    clinics = pd.DataFrame(
        {
            "title": ["Clinic A"],
            "zip": ["07087"],
            "latitude": [40.0],
            "longitude": [-74.0],
            "earliest_review_date": [
                "2020-01-01"
            ],
        }
    )

    timeline = pd.DataFrame(
        {
            "title": ["Clinic A", "Clinic A"],
            "zip": ["07087", "07087"],
            "est_founded": [2010, 2012],
        }
    )

    with pytest.raises(
        ValueError,
        match="duplicate title and ZIP keys",
    ):
        prepare_legacy_clinics(
            clinics,
            timeline,
        )
