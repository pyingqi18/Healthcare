import pandas as pd
import pytest

from medical_ratings.legacy import (
    prepare_legacy_reviews,
)


def make_clinics() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": [
                "a",
                "b",
                "c1",
                "c2",
                "canada",
            ],
            "normalized_title": [
                "clinic a",
                "clinic b",
                "shared clinic",
                "shared clinic",
                "clinic canada",
            ],
            "normalized_zip": [
                "07087",
                pd.NA,
                "10001",
                "10002",
                pd.NA,
            ],
            "title_zip_key": [
                "clinic a|07087",
                pd.NA,
                "shared clinic|10001",
                "shared clinic|10002",
                pd.NA,
            ],
        }
    )


def test_prepare_legacy_reviews_linkage_paths() -> None:
    reviews = pd.DataFrame(
        {
            "shop_title": [
                "Clinic A",
                "Clinic B",
                "Shared Clinic",
                "Clinic A",
                "Clinic Canada",
                None,
            ],
            "shop_zip": [
                7087.0,
                None,
                None,
                "99999",
                "L2A 2S7",
                "10001",
            ],
            "date": [
                "2020-01-01",
                "2020-01-02",
                "2020-01-03",
                "2020-01-04",
                "2020-01-05",
                "2020-01-06",
            ],
            "rating": [5, 4, 3, 2, 1, 5],
        }
    )

    result = prepare_legacy_reviews(
        reviews,
        make_clinics(),
    )

    assert result["clinic_key"].tolist() == [
        "a",
        "b",
        pd.NA,
        pd.NA,
        "canada",
        pd.NA,
    ]

    assert result[
        "review_linkage_method"
    ].tolist() == [
        "title_zip",
        "missing_zip_unique_title",
        "missing_zip_ambiguous_title",
        "zip_mismatch_unique_title",
        "non_us_postal_unique_title",
        "missing_title",
    ]

    assert result[
        "zip_mismatch_with_unique_title"
    ].tolist() == [
        False,
        False,
        False,
        True,
        False,
        False,
    ]

    assert result[
        "review_linkage_status"
    ].tolist() == [
        "matched",
        "matched",
        "unmatched",
        "unmatched",
        "matched",
        "unmatched",
    ]

    assert result["review_date"].notna().all()
    assert result["rating_numeric"].tolist() == [
        5,
        4,
        3,
        2,
        1,
        5,
    ]


def test_duplicate_clinic_pair_is_rejected() -> None:
    clinics = make_clinics()

    duplicate = clinics.iloc[[0]].copy()
    duplicate["clinic_key"] = "different-key"

    clinics = pd.concat(
        [clinics, duplicate],
        ignore_index=True,
    )

    reviews = pd.DataFrame(
        {
            "shop_title": ["Clinic A"],
            "shop_zip": ["07087"],
            "date": ["2020-01-01"],
            "rating": [5],
        }
    )

    with pytest.raises(
        ValueError,
        match="title and ZIP keys are not unique",
    ):
        prepare_legacy_reviews(
            reviews,
            clinics,
        )