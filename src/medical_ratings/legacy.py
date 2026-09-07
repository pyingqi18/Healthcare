"""Preparation of legacy clinic data."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from medical_ratings.identifiers import (
    build_clinic_key,
    normalize_name,
    normalize_zip,
)


def prepare_legacy_clinics(
    clinics: pd.DataFrame,
    timeline: pd.DataFrame,
    current_year: int | None = None,
) -> pd.DataFrame:
    """Build a location-safe legacy clinic table."""

    required_clinic_columns = {
        "title",
        "zip",
        "latitude",
        "longitude",
        "earliest_review_date",
    }
    required_timeline_columns = {
        "title",
        "zip",
        "est_founded",
    }

    missing_clinic_columns = (
        required_clinic_columns
        - set(clinics.columns)
    )
    missing_timeline_columns = (
        required_timeline_columns
        - set(timeline.columns)
    )

    if missing_clinic_columns:
        raise KeyError(
            "Missing clinic columns: "
            f"{sorted(missing_clinic_columns)}"
        )

    if missing_timeline_columns:
        raise KeyError(
            "Missing timeline columns: "
            f"{sorted(missing_timeline_columns)}"
        )

    result = clinics.copy()
    timeline_work = timeline.copy()

    for data in (result, timeline_work):
        data["normalized_title"] = (
            data["title"].map(normalize_name)
        )
        data["normalized_zip"] = (
            data["zip"].map(normalize_zip)
        )

        complete = (
            data["normalized_title"].notna()
            & data["normalized_zip"].notna()
        )

        data["title_zip_key"] = pd.Series(
            pd.NA,
            index=data.index,
            dtype="string",
        )

        data.loc[complete, "title_zip_key"] = (
            data.loc[complete, "normalized_title"]
            + "|"
            + data.loc[complete, "normalized_zip"]
        )

    complete_timeline = timeline_work.dropna(
        subset=["title_zip_key"]
    ).copy()

    if complete_timeline[
        "title_zip_key"
    ].duplicated().any():
        raise ValueError(
            "Timeline contains duplicate title and ZIP keys"
        )

    if result[
        "title_zip_key"
    ].dropna().duplicated().any():
        raise ValueError(
            "Clinic table contains duplicate title and ZIP keys"
        )

    timeline_year_map = complete_timeline.set_index(
        "title_zip_key"
    )["est_founded"]

    matched = result["title_zip_key"].isin(
        complete_timeline["title_zip_key"]
    )

    result["timeline_match_method"] = "unmatched"
    result.loc[
        matched,
        "timeline_match_method",
    ] = "title_zip"

    result["website_founded_year_raw"] = (
        result["title_zip_key"].map(
            timeline_year_map
        )
    )

    numeric_year = pd.to_numeric(
        result["website_founded_year_raw"],
        errors="coerce",
    )

    maximum_year = (
        current_year
        if current_year is not None
        else datetime.now().year
    )

    valid_year = (
        numeric_year.between(1800, maximum_year)
        & (numeric_year % 1 == 0)
    )

    result["website_founded_year"] = (
        numeric_year.where(valid_year)
        .astype("Int64")
    )

    result["website_founded_date_proxy"] = (
        pd.to_datetime(
            result["website_founded_year"]
            .astype("string")
            + "-12-31",
            errors="coerce",
        )
    )

    result["earliest_review_date_parsed"] = (
        pd.to_datetime(
            result["earliest_review_date"],
            errors="coerce",
        )
    )

    website_date = result[
        "website_founded_date_proxy"
    ]
    review_date = result[
        "earliest_review_date_parsed"
    ]

    result["entry_date_proxy"] = pd.concat(
        [website_date, review_date],
        axis=1,
    ).min(axis=1)

    result["entry_date_source"] = "missing"

    website_only = (
        website_date.notna()
        & review_date.isna()
    )
    review_only = (
        website_date.isna()
        & review_date.notna()
    )
    website_earlier = (
        website_date.notna()
        & review_date.notna()
        & (website_date < review_date)
    )
    review_earlier = (
        website_date.notna()
        & review_date.notna()
        & (review_date < website_date)
    )
    same_date = (
        website_date.notna()
        & review_date.notna()
        & (website_date == review_date)
    )

    result.loc[
        website_only | website_earlier,
        "entry_date_source",
    ] = "website"

    result.loc[
        review_only | review_earlier,
        "entry_date_source",
    ] = "first_review"

    result.loc[
        same_date,
        "entry_date_source",
    ] = "same_date"

    result["clinic_key"] = result.apply(
        lambda row: build_clinic_key(
            row.to_dict()
        ),
        axis=1,
    )

    duplicated_keys = result[
        "clinic_key"
    ].duplicated(keep=False)

    if duplicated_keys.any():
        raise ValueError(
            "Prepared clinic_key values are not unique. "
            f"Duplicate rows: "
            f"{int(duplicated_keys.sum())}"
        )

    return result


def prepare_legacy_reviews(
    reviews: pd.DataFrame,
    clinics: pd.DataFrame,
) -> pd.DataFrame:
    """Link legacy reviews to prepared clinic identities."""

    required_review_columns = {
        "shop_title",
        "shop_zip",
        "date",
        "rating",
    }
    required_clinic_columns = {
        "clinic_key",
        "normalized_title",
        "normalized_zip",
        "title_zip_key",
    }

    missing_review_columns = (
        required_review_columns
        - set(reviews.columns)
    )
    missing_clinic_columns = (
        required_clinic_columns
        - set(clinics.columns)
    )

    if missing_review_columns:
        raise KeyError(
            "Missing review columns: "
            f"{sorted(missing_review_columns)}"
        )

    if missing_clinic_columns:
        raise KeyError(
            "Missing prepared clinic columns: "
            f"{sorted(missing_clinic_columns)}"
        )

    if clinics["clinic_key"].duplicated().any():
        raise ValueError(
            "Prepared clinic_key values are not unique"
        )

    complete_clinics = clinics.dropna(
        subset=["title_zip_key"]
    ).copy()

    if complete_clinics[
        "title_zip_key"
    ].duplicated().any():
        raise ValueError(
            "Prepared clinic title and ZIP keys "
            "are not unique"
        )

    pair_map = complete_clinics.set_index(
        "title_zip_key"
    )["clinic_key"]

    clinic_title_counts = (
        clinics.dropna(
            subset=["normalized_title"]
        )
        .groupby("normalized_title")[
            "clinic_key"
        ]
        .nunique()
    )

    unique_titles = set(
        clinic_title_counts[
            clinic_title_counts == 1
        ].index
    )

    unique_title_map = (
        clinics.loc[
            clinics["normalized_title"].isin(
                unique_titles
            ),
            ["normalized_title", "clinic_key"],
        ]
        .drop_duplicates(
            subset=["normalized_title"]
        )
        .set_index("normalized_title")[
            "clinic_key"
        ]
    )

    result = reviews.copy()

    result["normalized_shop_title"] = (
        result["shop_title"].map(normalize_name)
    )
    result["normalized_shop_zip"] = (
        result["shop_zip"].map(normalize_zip)
    )

    raw_zip_text = (
        result["shop_zip"]
        .astype("string")
        .str.strip()
    )

    result["non_us_postal_code"] = (
        raw_zip_text.str.contains(
            r"[A-Za-z]",
            regex=True,
            na=False,
        )
    )

    complete_review_key = (
        result["normalized_shop_title"].notna()
        & result["normalized_shop_zip"].notna()
    )

    result["review_title_zip_key"] = pd.Series(
        pd.NA,
        index=result.index,
        dtype="string",
    )

    result.loc[
        complete_review_key,
        "review_title_zip_key",
    ] = (
        result.loc[
            complete_review_key,
            "normalized_shop_title",
        ]
        + "|"
        + result.loc[
            complete_review_key,
            "normalized_shop_zip",
        ]
    )

    result["clinic_key"] = (
        result["review_title_zip_key"]
        .map(pair_map)
        .astype("string")
    )

    result["review_linkage_method"] = "unclassified"

    exact_match = result["clinic_key"].notna()

    result.loc[
        exact_match,
        "review_linkage_method",
    ] = "title_zip"

    missing_title = (
        result["normalized_shop_title"].isna()
    )

    result.loc[
        missing_title,
        "review_linkage_method",
    ] = "missing_title"

    complete_unmatched = (
        complete_review_key
        & result["clinic_key"].isna()
    )

    result.loc[
        complete_unmatched,
        "review_linkage_method",
    ] = "unmatched_title_zip"

    zip_mismatch_unique_title = (
        complete_unmatched
        & result["normalized_shop_title"].isin(
            unique_titles
        )
    )

    result.loc[
        zip_mismatch_unique_title,
        "review_linkage_method",
    ] = "zip_mismatch_unique_title"

    result["zip_mismatch_with_unique_title"] = (
        zip_mismatch_unique_title
    )

    missing_zip = (
        result["normalized_shop_title"].notna()
        & result["normalized_shop_zip"].isna()
    )

    unique_title_match = (
        missing_zip
        & result["normalized_shop_title"].isin(
            unique_titles
        )
    )

    result.loc[
        unique_title_match,
        "clinic_key",
    ] = (
        result.loc[
            unique_title_match,
            "normalized_shop_title",
        ]
        .map(unique_title_map)
        .astype("string")
    )

    regular_missing_zip_match = (
        unique_title_match
        & ~result["non_us_postal_code"]
    )

    result.loc[
        regular_missing_zip_match,
        "review_linkage_method",
    ] = "missing_zip_unique_title"

    non_us_match = (
        unique_title_match
        & result["non_us_postal_code"]
    )

    result.loc[
        non_us_match,
        "review_linkage_method",
    ] = "non_us_postal_unique_title"

    ambiguous_missing_zip = (
        missing_zip
        & result["normalized_shop_title"].map(
            clinic_title_counts
        ).fillna(0).gt(1)
    )

    result.loc[
        ambiguous_missing_zip,
        "review_linkage_method",
    ] = "missing_zip_ambiguous_title"

    missing_zip_no_title_match = (
        missing_zip
        & result["normalized_shop_title"].map(
            clinic_title_counts
        ).fillna(0).eq(0)
    )

    result.loc[
        missing_zip_no_title_match,
        "review_linkage_method",
    ] = "missing_zip_no_title_match"

    result["review_linkage_status"] = (
        result["clinic_key"]
        .notna()
        .map(
            {
                True: "matched",
                False: "unmatched",
            }
        )
    )

    result["review_date"] = pd.to_datetime(
        result["date"],
        errors="coerce",
    )

    result["rating_numeric"] = pd.to_numeric(
        result["rating"],
        errors="coerce",
    )

    return result