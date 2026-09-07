from collections import Counter
from pathlib import Path

import pandas as pd
import pytest


pytestmark = pytest.mark.real_data

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CLINICS_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "legacy_v1"
    / "clinics_prepared.csv"
)

REVIEWS_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "legacy_v1"
    / "reviews_prepared.csv"
)


@pytest.fixture(scope="module")
def review_metrics() -> dict[str, object]:
    assert CLINICS_PATH.is_file()
    assert REVIEWS_PATH.is_file()

    clinics = pd.read_csv(
        CLINICS_PATH,
        usecols=["clinic_key"],
        dtype={"clinic_key": "string"},
    )

    valid_clinic_keys = set(
        clinics["clinic_key"].dropna()
    )

    columns = set(
        pd.read_csv(
            REVIEWS_PATH,
            nrows=0,
        ).columns
    )

    required_columns = {
        "clinic_key",
        "review_linkage_method",
        "review_linkage_status",
        "review_date",
        "rating_numeric",
        "non_us_postal_code",
        "zip_mismatch_with_unique_title",
    }

    missing_columns = required_columns - columns

    assert not missing_columns, (
        f"Missing review columns: "
        f"{sorted(missing_columns)}"
    )

    total_rows = 0
    matched_rows = 0
    valid_date_rows = 0
    valid_rating_rows = 0
    non_us_rows = 0
    non_us_unmatched_rows = 0
    zip_mismatch_rows = 0
    linkage_counts: Counter[str] = Counter()
    unknown_clinic_keys: set[str] = set()
    clinic_keys_with_reviews: set[str] = set()

    for chunk in pd.read_csv(
        REVIEWS_PATH,
        chunksize=100_000,
        low_memory=False,
        dtype={
            "shop_zip": "string",
            "normalized_shop_zip": "string",
            "clinic_key": "string",
        },
    ):
        total_rows += len(chunk)

        matched = (
            chunk["review_linkage_status"]
            == "matched"
        )
        matched_rows += int(matched.sum())

        linkage_counts.update(
            chunk[
                "review_linkage_method"
            ].value_counts().to_dict()
        )

        review_date = pd.to_datetime(
            chunk["review_date"],
            errors="coerce",
        )
        valid_date_rows += int(
            review_date.notna().sum()
        )

        rating = pd.to_numeric(
            chunk["rating_numeric"],
            errors="coerce",
        )
        valid_rating_rows += int(
            (
                rating.notna()
                & rating.between(1, 5)
            ).sum()
        )

        non_us = (
            chunk["non_us_postal_code"]
            .astype("string")
            .str.lower()
            .map(
                {
                    "true": True,
                    "false": False,
                }
            )
            .fillna(False)
        )

        non_us_rows += int(non_us.sum())
        non_us_unmatched_rows += int(
            (non_us & ~matched).sum()
        )

        zip_mismatch = (
            chunk[
                "zip_mismatch_with_unique_title"
            ]
            .astype("string")
            .str.lower()
            .eq("true")
        )

        zip_mismatch_rows += int(
            zip_mismatch.sum()
        )

        chunk_keys = set(
            chunk["clinic_key"].dropna()
        )

        unknown_clinic_keys.update(
            chunk_keys - valid_clinic_keys
        )
        clinic_keys_with_reviews.update(
            chunk_keys
        )

    return {
        "total_rows": total_rows,
        "matched_rows": matched_rows,
        "valid_date_rows": valid_date_rows,
        "valid_rating_rows": valid_rating_rows,
        "non_us_rows": non_us_rows,
        "non_us_unmatched_rows": (
            non_us_unmatched_rows
        ),
        "zip_mismatch_rows": zip_mismatch_rows,
        "linkage_counts": dict(linkage_counts),
        "unknown_clinic_keys": (
            unknown_clinic_keys
        ),
        "clinic_keys_with_reviews": len(
            clinic_keys_with_reviews
        ),
        "clinic_keys_without_reviews": (
            len(valid_clinic_keys)
            - len(clinic_keys_with_reviews)
        ),
    }


def test_review_rows_are_preserved(
    review_metrics: dict[str, object],
) -> None:
    assert review_metrics["total_rows"] == 769515
    assert review_metrics["matched_rows"] == 769515


def test_all_reviews_use_known_clinic_keys(
    review_metrics: dict[str, object],
) -> None:
    assert not review_metrics[
        "unknown_clinic_keys"
    ]
    assert (
        review_metrics[
            "clinic_keys_with_reviews"
        ]
        == 4182
    )
    assert (
        review_metrics[
            "clinic_keys_without_reviews"
        ]
        == 1596
    )


def test_review_linkage_paths(
    review_metrics: dict[str, object],
) -> None:
    assert review_metrics[
        "linkage_counts"
    ] == {
        "title_zip": 757111,
        "missing_zip_unique_title": 11952,
        "non_us_postal_unique_title": 452,
    }
    assert (
        review_metrics["zip_mismatch_rows"]
        == 0
    )


def test_review_dates_and_ratings_are_valid(
    review_metrics: dict[str, object],
) -> None:
    assert (
        review_metrics["valid_date_rows"]
        == 769515
    )
    assert (
        review_metrics["valid_rating_rows"]
        == 769515
    )


def test_non_us_reviews_are_identified(
    review_metrics: dict[str, object],
) -> None:
    assert review_metrics["non_us_rows"] == 452
    assert (
        review_metrics[
            "non_us_unmatched_rows"
        ]
        == 0
    )