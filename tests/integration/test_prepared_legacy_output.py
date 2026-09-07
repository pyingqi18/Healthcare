from pathlib import Path

import pandas as pd
import pytest


pytestmark = pytest.mark.real_data

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PREPARED_CLINICS_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "legacy_v1"
    / "clinics_prepared.csv"
)


@pytest.fixture(scope="module")
def prepared_clinics() -> pd.DataFrame:
    assert PREPARED_CLINICS_PATH.is_file(), (
        "Prepared clinic file does not exist. "
        "Run scripts/00_prepare_legacy_data.py first."
    )

    return pd.read_csv(
        PREPARED_CLINICS_PATH,
        low_memory=False,
        dtype={
            "zip": "string",
            "normalized_zip": "string",
            "title_zip_key": "string",
            "clinic_key": "string",
        },
    )


def test_prepared_clinic_schema(
    prepared_clinics: pd.DataFrame,
) -> None:
    required_columns = {
        "clinic_key",
        "normalized_title",
        "normalized_zip",
        "title_zip_key",
        "timeline_match_method",
        "website_founded_year",
        "website_founded_date_proxy",
        "earliest_review_date_parsed",
        "entry_date_proxy",
        "entry_date_source",
    }

    missing = (
        required_columns
        - set(prepared_clinics.columns)
    )

    assert not missing, (
        f"Missing prepared columns: {sorted(missing)}"
    )


def test_prepared_clinic_identity_is_unique(
    prepared_clinics: pd.DataFrame,
) -> None:
    assert len(prepared_clinics) == 5778
    assert (
        prepared_clinics["clinic_key"]
        .notna()
        .all()
    )
    assert not (
        prepared_clinics["clinic_key"]
        .duplicated()
        .any()
    )
    assert (
        prepared_clinics["clinic_key"].nunique()
        == 5778
    )


def test_prepared_timeline_matches(
    prepared_clinics: pd.DataFrame,
) -> None:
    match_counts = (
        prepared_clinics[
            "timeline_match_method"
        ]
        .value_counts()
        .to_dict()
    )

    assert match_counts == {
        "unmatched": 4889,
        "title_zip": 889,
    }

    assert (
        prepared_clinics[
            "website_founded_date_proxy"
        ].notna().sum()
        == 409
    )


def test_prepared_entry_dates(
    prepared_clinics: pd.DataFrame,
) -> None:
    website_date = pd.to_datetime(
        prepared_clinics[
            "website_founded_date_proxy"
        ],
        errors="coerce",
    )
    review_date = pd.to_datetime(
        prepared_clinics[
            "earliest_review_date_parsed"
        ],
        errors="coerce",
    )
    entry_date = pd.to_datetime(
        prepared_clinics[
            "entry_date_proxy"
        ],
        errors="coerce",
    )

    expected_entry_date = pd.concat(
        [website_date, review_date],
        axis=1,
    ).min(axis=1)

    equal = (
        entry_date.eq(expected_entry_date)
        | (
            entry_date.isna()
            & expected_entry_date.isna()
        )
    )

    assert equal.all()
    assert review_date.notna().sum() == 4182
    assert entry_date.notna().sum() == 4249
    assert entry_date.isna().sum() == 1529

    source_counts = (
        prepared_clinics[
            "entry_date_source"
        ]
        .value_counts()
        .to_dict()
    )

    assert source_counts == {
        "first_review": 3927,
        "missing": 1529,
        "website": 322,
    }


def test_alphanumeric_postal_codes_are_not_us_zip(
    prepared_clinics: pd.DataFrame,
) -> None:
    raw_zip = (
        prepared_clinics["zip"]
        .fillna("")
        .str.strip()
    )

    alphanumeric_postal = raw_zip.str.contains(
        r"[A-Za-z]",
        regex=True,
    )

    assert alphanumeric_postal.sum() == 11

    assert (
        prepared_clinics.loc[
            alphanumeric_postal,
            "normalized_zip",
        ]
        .isna()
        .all()
    )

    assert (
        prepared_clinics.loc[
            alphanumeric_postal,
            "timeline_match_method",
        ]
        .eq("unmatched")
        .all()
    )