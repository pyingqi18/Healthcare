from pathlib import Path
from medical_ratings.identifiers import build_clinic_key
import pandas as pd
import pytest


LEGACY_DIR = Path(
    "data/legacy/dentist_LMS_keywords/output/final"
)

CLINICS_PATH = LEGACY_DIR / "final_merged_time.csv"
REVIEWS_PATH = LEGACY_DIR / "all_reviews_detailed.csv"

PREMERGE_CLINICS_PATH = (
    LEGACY_DIR
    / "final_processed_with_earliest_review.csv"
)

TIMELINE_PATH = (
    LEGACY_DIR
    / "timeline_data_final.csv"
)

pytestmark = pytest.mark.real_data


def test_required_legacy_files_exist() -> None:
    required_files = {
        "current clinic file": CLINICS_PATH,
        "review file": REVIEWS_PATH,
        "premerge clinic file": PREMERGE_CLINICS_PATH,
        "timeline file": TIMELINE_PATH,
    }

    missing_files = [
        f"{label}: {path}"
        for label, path in required_files.items()
        if not path.is_file()
    ]

    assert not missing_files, (
        "Missing required legacy files:\n"
        + "\n".join(missing_files)
    )


def test_legacy_clinic_schema() -> None:
    columns = set(
        pd.read_csv(CLINICS_PATH, nrows=0).columns
    )

    required = {
        "title",
        "zip",
        "latitude",
        "longitude",
        "start_date",
    }

    missing = required - columns

    assert not missing, (
        f"Missing clinic columns: {sorted(missing)}"
    )


def test_legacy_review_schema() -> None:
    columns = set(
        pd.read_csv(REVIEWS_PATH, nrows=0).columns
    )

    required = {
        "shop_title",
        "shop_zip",
        "date",
        "rating",
    }

    missing = required - columns

    assert not missing, (
        f"Missing review columns: {sorted(missing)}"
    )


def test_start_date_contains_valid_dates() -> None:
    data = pd.read_csv(
        CLINICS_PATH,
        usecols=["start_date"],
        low_memory=False,
    )

    parsed = pd.to_datetime(
        data["start_date"],
        errors="coerce",
    )

    assert parsed.notna().any(), (
        "No valid start_date values were found"
    )


def test_review_dates_contain_valid_values() -> None:
    valid_date_count = 0

    for chunk in pd.read_csv(
        REVIEWS_PATH,
        usecols=["date"],
        chunksize=100_000,
        low_memory=False,
    ):
        parsed = pd.to_datetime(
            chunk["date"],
            errors="coerce",
        )
        valid_date_count += int(parsed.notna().sum())

    assert valid_date_count > 0, (
        "No valid review dates were found"
    )


def test_review_ratings_are_in_valid_range() -> None:
    invalid_examples = []

    for chunk in pd.read_csv(
        REVIEWS_PATH,
        usecols=["rating"],
        chunksize=100_000,
        low_memory=False,
    ):
        ratings = pd.to_numeric(
            chunk["rating"],
            errors="coerce",
        )

        invalid = ratings[
            ratings.notna()
            & ~ratings.between(1, 5)
        ]

        if not invalid.empty:
            invalid_examples.extend(
                invalid.head(10).tolist()
            )

        if len(invalid_examples) >= 10:
            break

    assert not invalid_examples, (
        "Ratings outside the valid range 1 to 5: "
        f"{invalid_examples[:10]}"
    )

def test_all_clinics_can_build_stable_key() -> None:
    clinics = pd.read_csv(
        CLINICS_PATH,
        low_memory=False,
    )

    failed_rows = []

    for index, row in clinics.iterrows():
        try:
            build_clinic_key(row.to_dict())
        except (TypeError, ValueError):
            failed_rows.append(index)

    assert not failed_rows, (
        "Some clinics cannot build a clinic_key. "
        f"Failed row count: {len(failed_rows)}. "
        f"First row indices: {failed_rows[:10]}"
    )


def test_legacy_clinic_keys_have_known_duplicates() -> None:
    clinics = pd.read_csv(
        CLINICS_PATH,
        low_memory=False,
    )

    clinic_keys = clinics.apply(
        lambda row: build_clinic_key(row.to_dict()),
        axis=1,
    )

    duplicated = clinic_keys.duplicated(
        keep=False,
    )

    duplicate_row_count = int(duplicated.sum())
    duplicate_key_count = int(
        clinic_keys[duplicated].nunique()
    )

    assert duplicate_row_count == 22, (
        "The frozen legacy clinic input changed. "
        f"Expected 22 duplicate rows, found "
        f"{duplicate_row_count}."
    )

    assert duplicate_key_count == 11, (
        "The frozen legacy clinic input changed. "
        f"Expected 11 duplicate keys, found "
        f"{duplicate_key_count}."
    )

def test_premerge_clinic_input_structure() -> None:
    clinics = pd.read_csv(
        PREMERGE_CLINICS_PATH,
        low_memory=False,
    )

    required_columns = {
        "title",
        "zip",
        "address",
        "latitude",
        "longitude",
        "earliest_review_date",
    }

    missing_columns = (
        required_columns
        - set(clinics.columns)
    )

    assert len(clinics) == 5778, (
        "Unexpected premerge clinic row count. "
        f"Expected 5778, found {len(clinics)}."
    )

    assert not missing_columns, (
        "Missing premerge clinic columns: "
        f"{sorted(missing_columns)}"
    )


def test_timeline_input_structure() -> None:
    timeline = pd.read_csv(
        TIMELINE_PATH,
        low_memory=False,
    )

    required_columns = {
        "title",
        "zip",
        "address",
        "latitude",
        "longitude",
        "est_founded",
    }

    missing_columns = (
        required_columns
        - set(timeline.columns)
    )

    assert len(timeline) == 900, (
        "Unexpected timeline row count. "
        f"Expected 900, found {len(timeline)}."
    )

    assert not missing_columns, (
        "Missing timeline columns: "
        f"{sorted(missing_columns)}"
    )
