"""Diagnostics for deciding whether a panel is ready for regression."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd


def _boolean_mask(values: pd.Series) -> pd.Series:
    """Normalize common CSV boolean representations."""

    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False).astype(bool)
    return (
        values.astype("string")
        .str.strip()
        .str.lower()
        .isin({"true", "1", "yes"})
        .fillna(False)
    )


def _numeric_diagnostics(
    data: pd.DataFrame,
    column: str,
    entity_column: str,
) -> dict[str, int | float | None]:
    values = pd.to_numeric(data[column], errors="coerce")
    observed = values.notna()
    observed_data = pd.DataFrame(
        {
            entity_column: data.loc[observed, entity_column],
            "value": values.loc[observed],
        }
    )
    ranges = observed_data.groupby(entity_column)["value"].agg(
        lambda group: float(group.max() - group.min())
    )

    return {
        "observed_rows": int(observed.sum()),
        "missing_rows": int((~observed).sum()),
        "distinct_values": int(values.loc[observed].nunique()),
        "minimum": (
            float(values.loc[observed].min()) if observed.any() else None
        ),
        "maximum": (
            float(values.loc[observed].max()) if observed.any() else None
        ),
        "mean": (
            float(values.loc[observed].mean()) if observed.any() else None
        ),
        "standard_deviation": (
            float(values.loc[observed].std()) if observed.sum() > 1 else None
        ),
        "zero_rows": int(values.loc[observed].eq(0).sum()),
        "entities_with_within_variation": int(ranges.gt(0).sum()),
    }


def audit_regression_readiness(
    panel: pd.DataFrame,
    *,
    outcome: str = "dynamic_rating",
    exposures: Sequence[str] = (
        "log_entry_shock_inner_count",
        "log_density_inner_count",
    ),
    entity_column: str = "clinic_key",
    time_column: str = "year",
    market_column: str | None = None,
    analysis_mask_column: str = "analysis_period",
    spatial_mask_column: str = "spatial_analysis_eligible",
) -> dict[str, Any]:
    """Return schema, sample, and variation checks without fitting a model."""

    selected_market = market_column
    if selected_market is None:
        selected_market = next(
            (
                candidate
                for candidate in ("mapped_location", "search_location")
                if candidate in panel.columns
            ),
            None,
        )

    required = [
        entity_column,
        time_column,
        outcome,
        analysis_mask_column,
        spatial_mask_column,
        *exposures,
    ]
    if selected_market is not None:
        required.append(selected_market)

    missing_columns = sorted(
        column for column in required if column not in panel.columns
    )
    if selected_market is None:
        missing_columns.append("mapped_location_or_search_location")

    identity_available = all(
        column in panel.columns for column in (entity_column, time_column)
    )
    duplicate_entity_year_rows = (
        int(panel.duplicated([entity_column, time_column]).sum())
        if identity_available
        else None
    )

    analysis_mask = (
        _boolean_mask(panel[analysis_mask_column])
        if analysis_mask_column in panel.columns
        else pd.Series(False, index=panel.index)
    )
    spatial_mask = (
        _boolean_mask(panel[spatial_mask_column])
        if spatial_mask_column in panel.columns
        else pd.Series(False, index=panel.index)
    )
    eligible_mask = analysis_mask & spatial_mask

    model_columns = [
        entity_column,
        time_column,
        outcome,
        *exposures,
    ]
    if selected_market is not None:
        model_columns.append(selected_market)

    if all(column in panel.columns for column in model_columns):
        complete_model_mask = panel[model_columns].notna().all(axis=1)
        estimation_mask = eligible_mask & complete_model_mask
    else:
        estimation_mask = pd.Series(False, index=panel.index)

    diagnostics: dict[str, Any] = {}
    if entity_column in panel.columns:
        candidate_data = panel.loc[eligible_mask].copy()
        for column in (outcome, *exposures):
            if column in panel.columns:
                diagnostics[column] = _numeric_diagnostics(
                    candidate_data,
                    column,
                    entity_column,
                )

    alerts: list[str] = []
    if missing_columns:
        alerts.append("missing_model_columns")
    if duplicate_entity_year_rows:
        alerts.append("duplicate_entity_year_rows")
    outcome_diagnostics = diagnostics.get(outcome)
    if outcome_diagnostics is not None:
        if outcome_diagnostics["distinct_values"] < 2:
            alerts.append("outcome_has_no_cross_sectional_variation")
        if outcome_diagnostics["entities_with_within_variation"] == 0:
            alerts.append("outcome_has_no_within_entity_variation")
    for exposure in exposures:
        exposure_diagnostics = diagnostics.get(exposure)
        if exposure_diagnostics is None:
            continue
        if exposure_diagnostics["distinct_values"] < 2:
            alerts.append(f"{exposure}_has_no_cross_sectional_variation")
        if exposure_diagnostics["entities_with_within_variation"] == 0:
            alerts.append(f"{exposure}_has_no_within_entity_variation")

    ready = (
        not missing_columns
        and duplicate_entity_year_rows == 0
        and int(estimation_mask.sum()) > 0
        and not any("has_no_" in alert for alert in alerts)
    )

    years = (
        pd.to_numeric(panel[time_column], errors="coerce")
        if time_column in panel.columns
        else pd.Series(dtype="float64")
    )
    entities = (
        int(panel[entity_column].nunique(dropna=True))
        if entity_column in panel.columns
        else None
    )

    return {
        "regression_ready": ready,
        "target_specification": {
            "outcome": outcome,
            "exposures": list(exposures),
            "entity_column": entity_column,
            "time_column": time_column,
            "market_column": selected_market,
            "analysis_mask_column": analysis_mask_column,
            "spatial_mask_column": spatial_mask_column,
        },
        "schema": {
            "column_count": int(len(panel.columns)),
            "missing_model_columns": missing_columns,
            "duplicate_entity_year_rows": duplicate_entity_year_rows,
        },
        "sample": {
            "panel_rows": int(len(panel)),
            "clinic_count": entities,
            "minimum_year": int(years.min()) if years.notna().any() else None,
            "maximum_year": int(years.max()) if years.notna().any() else None,
            "analysis_period_rows": int(analysis_mask.sum()),
            "spatial_eligible_rows": int(spatial_mask.sum()),
            "analysis_and_spatial_eligible_rows": int(eligible_mask.sum()),
            "complete_estimation_rows": int(estimation_mask.sum()),
            "complete_estimation_clinics": (
                int(panel.loc[estimation_mask, entity_column].nunique())
                if entity_column in panel.columns
                else None
            ),
        },
        "variable_diagnostics": diagnostics,
        "alerts": alerts,
    }
