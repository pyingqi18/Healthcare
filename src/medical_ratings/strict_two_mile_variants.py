"""Single-change variants of the frozen strict 009a two-mile baseline."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from medical_ratings.strict_legacy_two_mile import (
    _resolve_entry_years,
    _resolve_market_values,
)


BASELINE_COUNT = "lag_entry_shock_2mi_count_strict_009a"
BASELINE_LOG = "log_lag_entry_shock_2mi_strict_009a"
CORRECTED_COUNT = "lag_entry_shock_2mi_count_strict_009a_excl_self"
CORRECTED_LOG = "log_lag_entry_shock_2mi_strict_009a_excl_self"


def build_strict_009a_self_excluded_exposure(
    strict_panel: pd.DataFrame,
    clinics: pd.DataFrame,
    *,
    clinic_key: str = "clinic_key",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Remove focal-clinic self-counting from an existing strict panel."""

    required_panel = {
        clinic_key,
        "year",
        "strict_009a_sample",
        BASELINE_COUNT,
        BASELINE_LOG,
    }
    missing_panel = required_panel - set(strict_panel.columns)
    if missing_panel:
        raise KeyError(f"Missing strict panel columns: {sorted(missing_panel)}")
    if clinic_key not in clinics.columns:
        raise KeyError(f"Clinics require {clinic_key}")
    if strict_panel.duplicated([clinic_key, "year"]).any():
        raise ValueError("Strict panel contains duplicate clinic-year rows")
    if clinics[clinic_key].duplicated().any():
        raise ValueError("Clinics contain duplicate clinic_key rows")

    entry_years, entry_date_source, fallback_rows = _resolve_entry_years(
        clinics
    )
    entry_year_by_clinic = pd.Series(
        entry_years.to_numpy(), index=clinics[clinic_key]
    )

    output = strict_panel.copy()
    baseline_count = pd.to_numeric(output[BASELINE_COUNT], errors="coerce")
    panel_year = pd.to_numeric(output["year"], errors="coerce")
    focal_entry_year = output[clinic_key].map(entry_year_by_clinic)
    strict_sample = output["strict_009a_sample"].eq(True)
    self_entry_row = (
        strict_sample
        & baseline_count.notna()
        & focal_entry_year.notna()
        & panel_year.eq(focal_entry_year + 1)
    )

    corrected_count = baseline_count.copy()
    corrected_count.loc[self_entry_row] = (
        corrected_count.loc[self_entry_row] - 1
    )
    if corrected_count.dropna().lt(0).any():
        raise ValueError("Self-excluded strict entry shock became negative")

    output[CORRECTED_COUNT] = corrected_count.round().astype("Int64")
    output[CORRECTED_LOG] = np.log1p(corrected_count)

    if not output[BASELINE_COUNT].isna().equals(output[CORRECTED_COUNT].isna()):
        raise ValueError("Self-exclusion changed exposure missingness")

    metadata: dict[str, Any] = {
        "analysis_status": "strict_single_defect_correction_not_final",
        "algorithm": "strict_009a_global_two_mile_self_excluded",
        "baseline_module": "medical_ratings.strict_legacy_two_mile",
        "variant_module": "medical_ratings.strict_two_mile_variants",
        "input_panel_rows": int(len(strict_panel)),
        "strict_sample_rows": int(strict_sample.sum()),
        "entry_date_source": entry_date_source,
        "entry_year_rows_filled_from_entry_date_proxy": int(fallback_rows),
        "entry_shock_self_excluded": True,
        "panel_rows_with_self_entry_removed": int(self_entry_row.sum()),
        "changed_from_strict_legacy": [
            "subtract the focal clinic from its own prior-year entry shock"
        ],
        "unchanged_strict_legacy_choices": [
            "strict 009a neighbor-pool membership",
            "fixed two-mile radius",
            "global neighbor query",
            "clinic-years from entry year through 2025",
            "clinic entity fixed effects",
            "clinic-clustered standard errors",
            "log_votes_dynamic control",
        ],
        "alerts": [
            "diagnostic single-change comparison, not a final estimate"
        ],
    }
    return output, metadata


def fit_strict_009a_self_excluded_entity_fe(
    panel: pd.DataFrame,
) -> tuple[Any, dict[str, Any]]:
    """Fit the strict Entity FE model using only the self-excluded shock."""

    try:
        from linearmodels.panel import PanelOLS
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    required = [
        "clinic_key",
        "year",
        "dynamic_rating",
        CORRECTED_LOG,
        "log_votes_dynamic",
        "strict_009a_sample",
    ]
    missing = [column for column in required if column not in panel.columns]
    if missing:
        raise KeyError(f"Missing strict variant columns: {missing}")

    model_data = panel.loc[panel["strict_009a_sample"].eq(True)].dropna(
        subset=required[:-1]
    ).copy()
    if model_data.duplicated(["clinic_key", "year"]).any():
        raise ValueError("Strict variant sample has duplicate clinic-year rows")
    if model_data.empty:
        raise ValueError("Strict variant regression sample is empty")

    model_data = model_data.set_index(["clinic_key", "year"]).sort_index()
    formula = (
        f"dynamic_rating ~ {CORRECTED_LOG} "
        "+ log_votes_dynamic + EntityEffects"
    )
    model = PanelOLS.from_formula(
        formula,
        data=model_data,
        drop_absorbed=True,
    )
    result = model.fit(cov_type="clustered", cluster_entity=True)
    metadata = {
        "analysis_status": "strict_single_defect_correction_not_final",
        "specification_id": "strict_009a_2mile_self_excluded_entity_fe",
        "baseline_specification_id": "009a_final_2mile_entity_fe_corrected_data",
        "formula": formula,
        "explicit_constant_included": False,
        "sample_rows": int(len(model_data)),
        "sample_clinics": int(
            model_data.index.get_level_values("clinic_key").nunique()
        ),
        "cluster": "clinic_key",
        "entity_effects": True,
        "time_effects": False,
        "market_year_effects": False,
        "density_included": False,
        "single_change": "focal-clinic self-entry is excluded",
        "remaining_concerns": [
            "global neighbor query is retained",
            "log_votes_dynamic may be post-treatment",
        ],
    }
    return result, metadata


def fit_strict_009a_self_excluded_entity_year_fe(
    panel: pd.DataFrame,
) -> tuple[Any, dict[str, Any]]:
    """Add common year effects to the strict self-excluded specification."""

    try:
        from linearmodels.panel import PanelOLS
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    required = [
        "clinic_key",
        "year",
        "dynamic_rating",
        CORRECTED_LOG,
        "log_votes_dynamic",
        "strict_009a_sample",
    ]
    missing = [column for column in required if column not in panel.columns]
    if missing:
        raise KeyError(f"Missing strict year-FE columns: {missing}")

    model_data = panel.loc[panel["strict_009a_sample"].eq(True)].dropna(
        subset=required[:-1]
    ).copy()
    if model_data.duplicated(["clinic_key", "year"]).any():
        raise ValueError("Strict year-FE sample has duplicate clinic-year rows")
    if model_data.empty:
        raise ValueError("Strict year-FE regression sample is empty")

    model_data = model_data.set_index(["clinic_key", "year"]).sort_index()
    formula = (
        f"dynamic_rating ~ {CORRECTED_LOG} "
        "+ log_votes_dynamic + EntityEffects + TimeEffects"
    )
    model = PanelOLS.from_formula(
        formula,
        data=model_data,
        drop_absorbed=True,
    )
    result = model.fit(cov_type="clustered", cluster_entity=True)
    metadata = {
        "analysis_status": "strict_fixed_effect_comparison_not_final",
        "specification_id": (
            "strict_009a_2mile_self_excluded_entity_year_fe"
        ),
        "baseline_specification_id": (
            "strict_009a_2mile_self_excluded_entity_fe"
        ),
        "formula": formula,
        "explicit_constant_included": False,
        "sample_rows": int(len(model_data)),
        "sample_clinics": int(
            model_data.index.get_level_values("clinic_key").nunique()
        ),
        "year_count": int(
            model_data.index.get_level_values("year").nunique()
        ),
        "cluster": "clinic_key",
        "entity_effects": True,
        "time_effects": True,
        "market_year_effects": False,
        "density_included": False,
        "single_change": "add common year fixed effects",
        "remaining_concerns": [
            "global neighbor query is retained",
            "log_votes_dynamic may be post-treatment",
        ],
    }
    return result, metadata


def fit_strict_009a_self_excluded_entity_market_year_fe(
    panel: pd.DataFrame,
    clinics: pd.DataFrame,
    *,
    clinic_key: str = "clinic_key",
) -> tuple[Any, dict[str, Any]]:
    """Replace common year effects with strict ZIP-market-by-year effects."""

    try:
        from linearmodels.panel import PanelOLS
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    required = [
        clinic_key,
        "year",
        "dynamic_rating",
        CORRECTED_LOG,
        "log_votes_dynamic",
        "strict_009a_sample",
    ]
    missing = [column for column in required if column not in panel.columns]
    if missing:
        raise KeyError(f"Missing strict market-year columns: {missing}")
    if clinic_key not in clinics.columns:
        raise KeyError(f"Clinics require {clinic_key}")
    if clinics[clinic_key].duplicated().any():
        raise ValueError("Clinics contain duplicate clinic_key rows")

    market_values, market_source, _ = _resolve_market_values(clinics)
    market_by_clinic = pd.Series(
        market_values.to_numpy(), index=clinics[clinic_key]
    )
    model_data = panel.loc[panel["strict_009a_sample"].eq(True)].dropna(
        subset=required[:-1]
    ).copy()
    if model_data.duplicated([clinic_key, "year"]).any():
        raise ValueError(
            "Strict market-year sample has duplicate clinic-year rows"
        )
    if model_data.empty:
        raise ValueError("Strict market-year regression sample is empty")

    model_data["strict_market"] = model_data[clinic_key].map(
        market_by_clinic
    )
    if model_data["strict_market"].isna().any():
        missing_market_clinics = int(
            model_data.loc[
                model_data["strict_market"].isna(), clinic_key
            ].nunique()
        )
        raise ValueError(
            "Strict regression sample contains clinics without legacy ZIP "
            f"market mapping: {missing_market_clinics}"
        )

    model_data["market_year"] = (
        model_data["strict_market"].astype(str)
        + "_"
        + model_data["year"].astype(str)
    )
    model_data = model_data.set_index([clinic_key, "year"]).sort_index()
    exogenous = model_data[[CORRECTED_LOG, "log_votes_dynamic"]]
    market_year = pd.DataFrame(
        model_data["market_year"].astype("category").cat.codes,
        index=model_data.index,
        columns=["market_year"],
    )
    model = PanelOLS(
        model_data["dynamic_rating"],
        exogenous,
        entity_effects=True,
        other_effects=market_year,
        drop_absorbed=True,
    )
    result = model.fit(cov_type="clustered", cluster_entity=True)
    metadata = {
        "analysis_status": "strict_fixed_effect_comparison_not_final",
        "specification_id": (
            "strict_009a_2mile_self_excluded_entity_market_year_fe"
        ),
        "baseline_specification_id": (
            "strict_009a_2mile_self_excluded_entity_year_fe"
        ),
        "formula": (
            f"dynamic_rating ~ {CORRECTED_LOG} + log_votes_dynamic "
            "+ EntityEffects + MarketYearEffects(strict ZIP market x year)"
        ),
        "explicit_constant_included": False,
        "sample_rows": int(len(model_data)),
        "sample_clinics": int(
            model_data.index.get_level_values(clinic_key).nunique()
        ),
        "year_count": int(
            model_data.index.get_level_values("year").nunique()
        ),
        "market_source": market_source,
        "market_count": int(model_data["strict_market"].nunique()),
        "market_year_effect_count": int(
            model_data["market_year"].nunique()
        ),
        "cluster": clinic_key,
        "entity_effects": True,
        "time_effects": False,
        "market_year_effects": True,
        "density_included": False,
        "single_change_from_entity_year": (
            "replace common year effects with strict ZIP-market-by-year effects"
        ),
        "remaining_concerns": [
            "global neighbor query is retained",
            "log_votes_dynamic may be post-treatment",
        ],
    }
    return result, metadata
