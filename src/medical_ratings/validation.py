"""Data validation and reconciliation utilities."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


STAR_COLUMNS = [f"rating_{star}_star" for star in range(1, 6)]


def add_rating_reconciliation(df: pd.DataFrame) -> pd.DataFrame:
    """Add rating-count diagnostics without dropping discrepant records."""

    required = ["votes_count", *STAR_COLUMNS]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise KeyError(f"Missing rating columns: {missing}")

    result = df.copy()
    for column in required:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result["star_sum"] = result[STAR_COLUMNS].sum(axis=1, min_count=1)
    result["rating_count_difference"] = result["votes_count"] - result["star_sum"]
    result["rating_count_status"] = np.select(
        [
            result["votes_count"].isna(),
            result["star_sum"].isna(),
            (result["votes_count"] > 0) & (result["star_sum"] == 0),
            result["rating_count_difference"] != 0,
        ],
        ["missing_votes", "missing_distribution", "distribution_unavailable", "mismatch"],
        default="reconciled",
    )
    return result


def assert_unique(df: pd.DataFrame, columns: Iterable[str], *, label: str) -> None:
    """Raise an informative error if a proposed key is not unique."""

    key = list(columns)
    duplicates = df[df.duplicated(key, keep=False)]
    if not duplicates.empty:
        raise ValueError(
            f"{label} is not unique on {key}; duplicate rows: {len(duplicates)}"
        )


def missingness_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return counts and shares of missing values by column."""

    return pd.DataFrame(
        {
            "missing_count": df.isna().sum(),
            "missing_share": df.isna().mean(),
            "dtype": df.dtypes.astype(str),
        }
    ).sort_values("missing_share", ascending=False)
