"""Audit sample differences between strict and compatible 009a baselines."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from medical_ratings.strict_legacy_two_mile import (
    _resolve_category_eligibility,
    _resolve_entry_years,
    _resolve_market_values,
)


def _boolean_mask(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(False).astype(bool)
    normalized = values.astype("string").str.strip().str.lower()
    invalid = normalized.notna() & ~normalized.isin(["true", "false"])
    if invalid.any():
        examples = sorted(normalized.loc[invalid].dropna().unique())[:5]
        raise ValueError(f"Invalid boolean values: {examples}")
    return normalized.eq("true").fillna(False)


def _require_unique_panel(panel: pd.DataFrame, label: str) -> None:
    required = {"clinic_key", "year"}
    missing = required - set(panel.columns)
    if missing:
        raise KeyError(f"{label} is missing columns: {sorted(missing)}")
    if panel.duplicated(["clinic_key", "year"]).any():
        raise ValueError(f"{label} contains duplicate clinic-year rows")


def _panel_keys(panel: pd.DataFrame) -> pd.MultiIndex:
    return pd.MultiIndex.from_frame(panel[["clinic_key", "year"]])


def _assert_same_panel_keys(
    base_panel: pd.DataFrame,
    comparison_panel: pd.DataFrame,
    label: str,
) -> None:
    base_keys = _panel_keys(base_panel)
    comparison_keys = _panel_keys(comparison_panel)
    if len(base_keys) != len(comparison_keys) or set(base_keys) != set(
        comparison_keys
    ):
        raise ValueError(f"{label} does not contain the same clinic-years as base panel")


def _regression_mask(
    panel: pd.DataFrame,
    *,
    exposure: str,
    strict: bool,
) -> pd.Series:
    required = {
        "clinic_key",
        "year",
        "dynamic_rating",
        "log_votes_dynamic",
        exposure,
    }
    if strict:
        required.add("strict_009a_sample")
    missing = required - set(panel.columns)
    if missing:
        raise KeyError(f"Regression panel is missing columns: {sorted(missing)}")

    mask = panel[list(required - {"strict_009a_sample"})].notna().all(axis=1)
    if strict:
        mask &= _boolean_mask(panel["strict_009a_sample"])
    else:
        if "analysis_period" in panel.columns:
            mask &= _boolean_mask(panel["analysis_period"])
        if "spatial_analysis_eligible" in panel.columns:
            mask &= _boolean_mask(panel["spatial_analysis_eligible"])
    return mask


def _join_reasons(row: pd.Series) -> str:
    reasons: list[str] = []
    if not row["strict_rating_observed"]:
        reasons.append("missing_rating_value")
    if not row["strict_category_eligible"]:
        reasons.append("category_not_legacy_eligible")
    if not row["strict_latitude_observed"]:
        reasons.append("missing_latitude")
    if not row["strict_longitude_observed"]:
        reasons.append("missing_longitude")
    if not row["strict_entry_year_observed"]:
        reasons.append("missing_entry_year")
    if not row["strict_market_observed"]:
        reasons.append("missing_market")
    return ";".join(reasons) if reasons else "eligible"


def _missing_panel_reason(row: pd.Series) -> str:
    if not row["strict_pool"] or row["in_corrected_panel"]:
        return "not_applicable"
    if row["entry_after_2025"]:
        return "entry_after_2025"
    if row["analysis_exclusion_reason"] != "eligible":
        return f"analysis_exclusion:{row['analysis_exclusion_reason']}"
    return "unexplained_missing_from_panel"


def audit_strict_legacy_sample(
    base_panel: pd.DataFrame,
    clinics: pd.DataFrame,
    strict_panel: pd.DataFrame,
    compatible_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Compare clinic pools and regression rows without changing any model."""

    for panel, label in [
        (base_panel, "base panel"),
        (strict_panel, "strict panel"),
        (compatible_panel, "compatible panel"),
    ]:
        _require_unique_panel(panel, label)
    _assert_same_panel_keys(base_panel, strict_panel, "strict panel")
    _assert_same_panel_keys(base_panel, compatible_panel, "compatible panel")

    required_clinics = {
        "clinic_key",
        "category",
        "rating_value",
        "latitude",
        "longitude",
    }
    missing_clinics = required_clinics - set(clinics.columns)
    if missing_clinics:
        raise KeyError(f"Clinics are missing columns: {sorted(missing_clinics)}")
    if clinics["clinic_key"].duplicated().any():
        raise ValueError("Clinics contain duplicate clinic_key rows")

    market_values, market_source, market_mapped_rows = (
        _resolve_market_values(clinics)
    )
    entry_years, entry_source, entry_fallback_rows = _resolve_entry_years(
        clinics
    )
    category_eligible, category_counts = _resolve_category_eligibility(
        clinics
    )
    rating = pd.to_numeric(clinics["rating_value"], errors="coerce")
    latitude = pd.to_numeric(clinics["latitude"], errors="coerce")
    longitude = pd.to_numeric(clinics["longitude"], errors="coerce")

    if "search_location" in clinics.columns:
        compatible_market = clinics["search_location"].astype("string").str.strip()
        compatible_market = compatible_market.mask(compatible_market.eq(""))
    else:
        compatible_market = market_values
    if "spatial_analysis_eligible" in clinics.columns:
        spatial_eligible = _boolean_mask(
            clinics["spatial_analysis_eligible"]
        )
    else:
        spatial_eligible = pd.Series(True, index=clinics.index)

    detail = pd.DataFrame(
        {
            "clinic_key": clinics["clinic_key"],
            "title": clinics.get("title", pd.Series(pd.NA, index=clinics.index)),
            "category": clinics["category"],
            "replacement_source": clinics.get(
                "replacement_source", pd.Series(pd.NA, index=clinics.index)
            ),
            "search_location": clinics.get(
                "search_location", pd.Series(pd.NA, index=clinics.index)
            ),
            "mapped_location": clinics.get(
                "mapped_location", pd.Series(pd.NA, index=clinics.index)
            ),
            "resolved_market": market_values,
            "entry_year": entry_years.astype("Int64"),
            "rating_value": rating,
            "latitude": latitude,
            "longitude": longitude,
            "analysis_exclusion_reason": clinics.get(
                "analysis_exclusion_reason",
                pd.Series("missing_reason_column", index=clinics.index),
            )
            .astype("string")
            .str.strip()
            .str.lower()
            .fillna("missing"),
            "spatial_exclusion_reason": clinics.get(
                "spatial_exclusion_reason",
                pd.Series("missing_reason_column", index=clinics.index),
            ),
            "spatial_analysis_eligible": spatial_eligible,
        }
    )
    detail["strict_rating_observed"] = rating.notna()
    detail["strict_category_eligible"] = category_eligible
    detail["strict_latitude_observed"] = latitude.notna()
    detail["strict_longitude_observed"] = longitude.notna()
    detail["strict_entry_year_observed"] = entry_years.notna()
    detail["strict_market_observed"] = market_values.notna()
    detail["strict_pool"] = detail[
        [
            "strict_rating_observed",
            "strict_category_eligible",
            "strict_latitude_observed",
            "strict_longitude_observed",
            "strict_entry_year_observed",
            "strict_market_observed",
        ]
    ].all(axis=1)
    detail["strict_pool_reason"] = detail.apply(_join_reasons, axis=1)

    valid_compatible_coordinate = (
        latitude.between(-90, 90)
        & longitude.between(-180, 180)
        & np.isfinite(latitude)
        & np.isfinite(longitude)
    )
    panel_clinic_keys = set(base_panel["clinic_key"].dropna())
    detail["in_corrected_panel"] = detail["clinic_key"].isin(
        panel_clinic_keys
    )
    detail["entry_after_2025"] = entry_years.gt(2025).fillna(False)
    detail["compatible_pool"] = (
        detail["in_corrected_panel"]
        & spatial_eligible
        & valid_compatible_coordinate
        & entry_years.notna()
        & compatible_market.notna()
    )
    detail["pool_relation"] = np.select(
        [
            detail["strict_pool"] & detail["compatible_pool"],
            detail["strict_pool"] & ~detail["compatible_pool"],
            ~detail["strict_pool"] & detail["compatible_pool"],
        ],
        ["both", "strict_only", "compatible_only"],
        default="neither",
    )
    detail["strict_pool_missing_panel_reason"] = detail.apply(
        _missing_panel_reason, axis=1
    )

    strict_mask = _regression_mask(
        strict_panel,
        exposure="log_lag_entry_shock_2mi_strict_009a",
        strict=True,
    )
    compatible_mask = _regression_mask(
        compatible_panel,
        exposure="log_lag_entry_shock_2mi",
        strict=False,
    )
    strict_rows = strict_panel.loc[strict_mask, ["clinic_key", "year"]].copy()
    compatible_rows = compatible_panel.loc[
        compatible_mask, ["clinic_key", "year"]
    ].copy()
    strict_keys = set(_panel_keys(strict_rows))
    compatible_keys = set(_panel_keys(compatible_rows))

    strict_by_clinic = strict_rows.groupby("clinic_key")["year"].agg(
        strict_regression_rows="size",
        strict_first_year="min",
        strict_last_year="max",
    )
    compatible_by_clinic = compatible_rows.groupby("clinic_key")["year"].agg(
        compatible_regression_rows="size",
        compatible_first_year="min",
        compatible_last_year="max",
    )
    detail = detail.merge(strict_by_clinic, on="clinic_key", how="left")
    detail = detail.merge(compatible_by_clinic, on="clinic_key", how="left")
    for column in ["strict_regression_rows", "compatible_regression_rows"]:
        detail[column] = detail[column].fillna(0).astype("Int64")

    missing_panel = detail.loc[
        detail["strict_pool"] & ~detail["in_corrected_panel"]
    ].copy()
    relation_summary = (
        detail.groupby("pool_relation", dropna=False)
        .size()
        .rename("clinic_count")
        .reset_index()
        .sort_values("pool_relation")
        .reset_index(drop=True)
    )

    missing_reason_counts = (
        missing_panel["strict_pool_missing_panel_reason"]
        .value_counts(dropna=False)
        .sort_index()
        .to_dict()
    )
    metadata: dict[str, Any] = {
        "analysis_status": "strict_legacy_sample_audit",
        "input_clinic_rows": int(len(clinics)),
        "base_panel_rows": int(len(base_panel)),
        "base_panel_clinics": int(base_panel["clinic_key"].nunique()),
        "strict_pool_clinics": int(detail["strict_pool"].sum()),
        "compatible_pool_clinics": int(detail["compatible_pool"].sum()),
        "pool_clinics_in_both": int(
            detail["pool_relation"].eq("both").sum()
        ),
        "strict_only_pool_clinics": int(
            detail["pool_relation"].eq("strict_only").sum()
        ),
        "compatible_only_pool_clinics": int(
            detail["pool_relation"].eq("compatible_only").sum()
        ),
        "strict_pool_clinics_missing_from_panel": int(len(missing_panel)),
        "strict_pool_missing_panel_reason_counts": {
            str(key): int(value) for key, value in missing_reason_counts.items()
        },
        "strict_regression_rows": int(len(strict_rows)),
        "strict_regression_clinics": int(strict_rows["clinic_key"].nunique()),
        "compatible_regression_rows": int(len(compatible_rows)),
        "compatible_regression_clinics": int(
            compatible_rows["clinic_key"].nunique()
        ),
        "regression_rows_in_both": int(len(strict_keys & compatible_keys)),
        "strict_only_regression_rows": int(
            len(strict_keys - compatible_keys)
        ),
        "compatible_only_regression_rows": int(
            len(compatible_keys - strict_keys)
        ),
        "market_source": market_source,
        "entry_date_source": entry_source,
        "market_rows_mapped_from_legacy_zip_rules": int(market_mapped_rows),
        "entry_rows_filled_from_entry_date_proxy": int(entry_fallback_rows),
        **category_counts,
        "automatic_sample_changes_performed": 0,
    }
    return detail, missing_panel, relation_summary, metadata
