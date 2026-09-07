"""Integration tests for the generated legacy clinic-year panel."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


PROCESSED_DIR = Path("data/processed/legacy_v1")
PANEL_PATH = PROCESSED_DIR / "clinic_year_panel.csv"
SUMMARY_PATH = PROCESSED_DIR / "clinic_year_panel_summary.json"

pytestmark = pytest.mark.real_data


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return pd.read_csv(PANEL_PATH, low_memory=False)


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def test_panel_outputs_exist() -> None:
    assert PANEL_PATH.is_file(), f"Missing panel file: {PANEL_PATH}"
    assert SUMMARY_PATH.is_file(), f"Missing panel summary: {SUMMARY_PATH}"


def test_panel_schema_and_identity(panel: pd.DataFrame) -> None:
    required = {
        "clinic_key",
        "year",
        "entry_year",
        "new_count",
        "new_stars",
        "low_review_count",
        "annual_rating",
        "annual_low_review_share",
        "cumulative_votes",
        "cumulative_stars",
        "dynamic_rating",
        "cumulative_low_review_share",
        "analysis_period",
        "spatial_analysis_eligible",
    }
    missing = required - set(panel.columns)
    assert not missing, f"Missing panel columns: {sorted(missing)}"
    assert not panel.duplicated(["clinic_key", "year"]).any()


def test_panel_year_window_and_age(panel: pd.DataFrame) -> None:
    assert int(panel["year"].min()) == 2008
    assert int(panel["year"].max()) == 2025
    assert panel["clinic_age"].ge(0).all()

    expected_analysis_period = panel["year"].between(2015, 2025)
    actual_analysis_period = (
        panel["analysis_period"]
        .astype("string")
        .str.lower()
        .eq("true")
    )
    assert np.array_equal(
        actual_analysis_period.fillna(False).to_numpy(dtype=bool),
        expected_analysis_period.to_numpy(dtype=bool),
    )


def test_panel_cumulative_outcomes(panel: pd.DataFrame) -> None:
    ordered = panel.sort_values(["clinic_key", "year"]).copy()
    grouped = ordered.groupby("clinic_key", sort=False)

    expected_votes = grouped["new_count"].cumsum()
    expected_stars = grouped["new_stars"].cumsum()
    expected_low_reviews = grouped["low_review_count"].cumsum()

    assert np.array_equal(
        ordered["cumulative_votes"].to_numpy(),
        expected_votes.to_numpy(),
    )
    assert np.allclose(
        ordered["cumulative_stars"],
        expected_stars,
    )
    assert np.array_equal(
        ordered["cumulative_low_reviews"].to_numpy(),
        expected_low_reviews.to_numpy(),
    )

    observed = ordered["cumulative_votes"].gt(0)
    expected_rating = (
        ordered.loc[observed, "cumulative_stars"]
        / ordered.loc[observed, "cumulative_votes"]
    )
    assert np.allclose(
        ordered.loc[observed, "dynamic_rating"],
        expected_rating,
    )
    assert ordered.loc[~observed, "dynamic_rating"].isna().all()


def test_panel_summary_reconciles(
    panel: pd.DataFrame,
    summary: dict,
) -> None:
    spatial_eligible = (
        panel["spatial_analysis_eligible"]
        .astype("string")
        .str.lower()
        .eq("true")
    )
    analysis_period = panel["year"].between(2015, 2025)

    assert summary["panel_rows"] == len(panel)
    assert summary["panel_clinic_rows"] == panel["clinic_key"].nunique()
    assert summary["panel_new_review_rows"] == int(panel["new_count"].sum())
    assert summary["analysis_period_panel_rows"] == int(
        analysis_period.sum()
    )
    assert summary["spatial_eligible_panel_rows"] == int(
        spatial_eligible.sum()
    )

    reconciled_reviews = (
        summary["panel_period_review_rows"]
        + summary["post_end_year_review_rows"]
        + summary["eligible_reviews_without_panel_clinic"]
    )
    assert reconciled_reviews == summary["analysis_eligible_review_rows"]
