"""Strict 009a two-mile baseline applied to corrected pipeline data."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


EARTH_RADIUS_MILES = 3958.8
LEGACY_KEYWORD_CATEGORIES = {
    "keywords_General_Dentist",
    "keywords_Special_Dentist",
    "keywords_Surgery_Dentist",
}
CORRECTED_REPLACEMENT_SOURCE = "corrected_location_rescrape"


def _legacy_009a_zip_number(value: Any) -> int | None:
    """Reproduce 009a's digit-only, first-five-character ZIP cleaning."""

    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if "-" in text:
        text = text.split("-", maxsplit=1)[0]
    digits = "".join(character for character in text if character.isdigit())[:5]
    return int(digits) if digits else None


def _legacy_009a_map_zip(value: Any) -> str | None:
    """Reproduce the explicit ZIP-to-market rules in notebook 009a."""

    zipcode = _legacy_009a_zip_number(value)
    if zipcode is None:
        return None
    if zipcode == 12953:
        return "Malone_NY_S"
    if zipcode == 12983:
        return "SaranacLake_NY_S"
    if 13200 <= zipcode <= 13299:
        return "Syracuse_NY_M"
    if 14200 <= zipcode <= 14299:
        return "Buffalo_NY_L"
    if 10000 <= zipcode <= 10499 or 11000 <= zipcode <= 11699:
        return "NYC_NY_L"
    if zipcode in {95501, 95502, 95503, 95534}:
        return "Eureka_CA_S"
    if zipcode == 95437:
        return "FortBragg_CA_S"
    if 95350 <= zipcode <= 95358:
        return "Modesto_CA_M"
    if 94100 <= zipcode <= 94188:
        return "SanFrancisco_CA_L"
    if 90000 <= zipcode <= 91699:
        return "LA_CA_L"
    if zipcode in {30474, 30475}:
        return "Vidalia_GA_S"
    if zipcode == 30577:
        return "Toccoa_GA_S"
    if 31200 <= zipcode <= 31299:
        return "Macon_GA_M"
    if 30900 <= zipcode <= 30999:
        return "Augusta_GA_L"
    if 30300 <= zipcode <= 30399 or 31100 <= zipcode <= 31199:
        return "Atlanta_GA_L"
    return None


def _resolve_market_values(
    clinics: pd.DataFrame,
) -> tuple[pd.Series, str, int]:
    """Rebuild mapped_location from ZIP exactly as notebook 009a did."""

    if "zip" not in clinics.columns:
        raise KeyError("Clinics require zip for strict 009a market mapping")
    resolved = clinics["zip"].map(_legacy_009a_map_zip).astype("string")
    return resolved, "legacy_009a_zip_mapping", int(resolved.notna().sum())


def _resolve_entry_years(
    clinics: pd.DataFrame,
) -> tuple[pd.Series, str, int]:
    """Use start_date first and fill its invalid rows from entry_date_proxy."""

    start_year = (
        pd.to_datetime(clinics["start_date"], errors="coerce").dt.year
        if "start_date" in clinics.columns
        else pd.Series(np.nan, index=clinics.index, dtype="float64")
    )
    proxy_year = (
        pd.to_datetime(clinics["entry_date_proxy"], errors="coerce").dt.year
        if "entry_date_proxy" in clinics.columns
        else pd.Series(np.nan, index=clinics.index, dtype="float64")
    )
    if "start_date" not in clinics.columns and "entry_date_proxy" not in clinics.columns:
        raise KeyError("Clinics require start_date or entry_date_proxy")

    fallback_mask = start_year.isna() & proxy_year.notna()
    resolved = start_year.fillna(proxy_year)
    if "start_date" in clinics.columns and "entry_date_proxy" in clinics.columns:
        source_label = "start_date_then_entry_date_proxy"
    elif "start_date" in clinics.columns:
        source_label = "start_date"
    else:
        source_label = "entry_date_proxy"
    return resolved, source_label, int(fallback_mask.sum())


def _resolve_category_eligibility(
    clinics: pd.DataFrame,
) -> tuple[pd.Series, dict[str, int]]:
    """Preserve 009a categories plus audited corrected replacements."""

    if "category" not in clinics.columns:
        raise KeyError("Clinics require category for strict 009a selection")
    category = clinics["category"].astype("string").str.strip()
    legacy_keyword = category.isin(LEGACY_KEYWORD_CATEGORIES)
    if "replacement_source" in clinics.columns:
        corrected_source = (
            clinics["replacement_source"]
            .astype("string")
            .str.strip()
            .eq(CORRECTED_REPLACEMENT_SOURCE)
        )
    else:
        corrected_source = pd.Series(False, index=clinics.index)
    corrected_category_observed = (
        corrected_source
        & category.notna()
        & category.ne("")
        & category.ne("Unknown")
    )
    eligible = legacy_keyword | corrected_category_observed
    counts = {
        "legacy_keyword_category_rows": int(legacy_keyword.sum()),
        "corrected_replacement_category_rows": int(
            corrected_category_observed.sum()
        ),
        "category_ineligible_rows": int((~eligible).sum()),
    }
    return eligible, counts


def build_strict_legacy_two_mile_on_corrected_data(
    panel: pd.DataFrame,
    clinics: pd.DataFrame,
    *,
    radius_miles: float = 2.0,
    clinic_key: str = "clinic_key",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply the 009a pool filter and exposure algorithm to corrected data.

    The original row-order identity and title/ZIP review join are intentionally
    replaced by the corrected stable clinic key and corrected panel outcome.
    All other feasible 009a two-mile sample and exposure choices are retained.
    """

    if radius_miles <= 0:
        raise ValueError("radius_miles must be positive")

    required_panel = {clinic_key, "year"}
    required_clinics = {
        clinic_key,
        "category",
        "rating_value",
        "latitude",
        "longitude",
    }
    missing_panel = required_panel - set(panel.columns)
    missing_clinics = required_clinics - set(clinics.columns)
    if missing_panel:
        raise KeyError(f"Missing panel columns: {sorted(missing_panel)}")
    if missing_clinics:
        raise KeyError(f"Missing clinic columns: {sorted(missing_clinics)}")
    if panel.duplicated([clinic_key, "year"]).any():
        raise ValueError("Panel contains duplicate clinic-year rows")
    if clinics[clinic_key].duplicated().any():
        raise ValueError("Clinics contain duplicate clinic_key rows")

    market_values, market_source, market_mapped_rows = (
        _resolve_market_values(clinics)
    )
    entry_years, entry_date_source, entry_date_fallback_rows = (
        _resolve_entry_years(clinics)
    )
    category_eligible, category_counts = _resolve_category_eligibility(
        clinics
    )

    try:
        from sklearn.neighbors import BallTree
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    clinic_work = clinics.copy()
    clinic_work["_rating_value"] = pd.to_numeric(
        clinic_work["rating_value"], errors="coerce"
    )
    clinic_work["_latitude"] = pd.to_numeric(
        clinic_work["latitude"], errors="coerce"
    )
    clinic_work["_longitude"] = pd.to_numeric(
        clinic_work["longitude"], errors="coerce"
    )
    clinic_work["_entry_year"] = entry_years
    clinic_work["_market_value"] = market_values
    clinic_work["_category_eligible"] = category_eligible

    # This reproduces 009a's df.dropna() pool. It deliberately ignores the
    # later spatial_analysis_eligible flag and does not require panel outcome.
    pool_mask = (
        clinic_work["_rating_value"].notna()
        & clinic_work["_category_eligible"]
        & clinic_work["_latitude"].notna()
        & clinic_work["_longitude"].notna()
        & clinic_work["_entry_year"].notna()
        & clinic_work["_market_value"].notna()
    )
    pool = clinic_work.loc[pool_mask].copy().reset_index(drop=True)
    if pool.empty:
        criterion_counts = {
            "rating_value_observed": int(
                clinic_work["_rating_value"].notna().sum()
            ),
            "category_eligible": int(
                clinic_work["_category_eligible"].sum()
            ),
            "latitude_observed": int(clinic_work["_latitude"].notna().sum()),
            "longitude_observed": int(
                clinic_work["_longitude"].notna().sum()
            ),
            "entry_year_observed": int(
                clinic_work["_entry_year"].notna().sum()
            ),
            "market_observed": int(
                clinic_work["_market_value"].notna().sum()
            ),
        }
        raise ValueError(
            "No clinics satisfy the strict 009a neighbor-pool filter; "
            f"criterion counts={criterion_counts}"
        )

    pool["_entry_year"] = pool["_entry_year"].astype(int)
    coordinates = np.radians(pool[["_latitude", "_longitude"]].to_numpy())
    tree = BallTree(coordinates, metric="haversine")
    neighbor_indices = tree.query_radius(
        coordinates,
        r=radius_miles / EARTH_RADIUS_MILES,
    )

    output = panel.copy().reset_index(drop=True)
    output["strict_009a_sample"] = False
    output["lag_entry_shock_2mi_count_strict_009a"] = pd.Series(
        pd.NA, index=output.index, dtype="Int64"
    )
    output["log_lag_entry_shock_2mi_strict_009a"] = np.nan
    output["lag_entry_shock_2mi_dummy_strict_009a"] = pd.Series(
        pd.NA, index=output.index, dtype="Int64"
    )
    output["density_2mi_total_strict_009a"] = pd.Series(
        pd.NA, index=output.index, dtype="Int64"
    )
    output["log_density_2mi_total_strict_009a"] = np.nan

    panel_groups = output.groupby(clinic_key, sort=False).indices
    pool_keys = pool[clinic_key].to_numpy()
    pool_years = pool["_entry_year"].to_numpy()
    pool_markets = pool["_market_value"].astype(str).to_numpy()

    cross_market_directed_links = 0
    self_contaminated_rows = 0
    pool_keys_missing_from_panel = 0

    for index, focal_key in enumerate(pool_keys):
        all_positions = panel_groups.get(focal_key)
        if all_positions is None:
            pool_keys_missing_from_panel += 1
            continue

        all_positions = np.asarray(all_positions)
        all_years = pd.to_numeric(
            output.loc[all_positions, "year"], errors="coerce"
        )
        legacy_year_mask = (
            all_years.ge(pool_years[index]) & all_years.le(2025)
        ).to_numpy()
        positions = all_positions[legacy_year_mask]
        years = all_years.iloc[np.flatnonzero(legacy_year_mask)].astype(int)
        if len(positions) == 0:
            continue

        neighbors = neighbor_indices[index]
        neighbor_years = pool_years[neighbors]
        cross_market_directed_links += int(
            np.sum(pool_markets[neighbors] != pool_markets[index])
        )
        lag_counts = np.asarray(
            [np.sum(neighbor_years == year - 1) for year in years],
            dtype=int,
        )
        density_counts = np.asarray(
            [max(0, int(np.sum(neighbor_years <= year)) - 1) for year in years],
            dtype=int,
        )

        output.loc[positions, "strict_009a_sample"] = True
        output.loc[
            positions, "lag_entry_shock_2mi_count_strict_009a"
        ] = lag_counts
        output.loc[
            positions, "log_lag_entry_shock_2mi_strict_009a"
        ] = np.log1p(lag_counts)
        output.loc[
            positions, "lag_entry_shock_2mi_dummy_strict_009a"
        ] = (lag_counts > 0).astype(int)
        output.loc[
            positions, "density_2mi_total_strict_009a"
        ] = density_counts
        output.loc[
            positions, "log_density_2mi_total_strict_009a"
        ] = np.log1p(density_counts)
        self_contaminated_rows += int(
            np.sum(years.to_numpy() == pool_years[index] + 1)
        )

    exposed = output["strict_009a_sample"]
    metadata: dict[str, Any] = {
        "analysis_status": "strict_legacy_on_corrected_data_not_final",
        "algorithm": "009a_global_two_mile_corrected_identity",
        "input_panel_rows": int(len(panel)),
        "input_clinic_rows": int(len(clinics)),
        "legacy_pool_clinics": int(len(pool)),
        "pool_clinics_missing_from_corrected_panel": int(
            pool_keys_missing_from_panel
        ),
        "panel_rows_in_strict_009a_sample": int(exposed.sum()),
        "panel_rows_outside_strict_009a_sample": int((~exposed).sum()),
        "radius_miles": float(radius_miles),
        "year_generation_end_inclusive": 2025,
        "market_column_used": market_source,
        "entry_date_column_used": entry_date_source,
        "market_rows_mapped_from_legacy_zip_rules": int(market_mapped_rows),
        "entry_year_rows_filled_from_entry_date_proxy": int(
            entry_date_fallback_rows
        ),
        "neighbor_scope": "global_across_markets",
        "current_rating_required_for_neighbor_pool": True,
        "legacy_category_filter_applied": True,
        **category_counts,
        "spatial_analysis_eligible_filter_applied": False,
        "analysis_period_filter_applied": False,
        "density_self_handling": "subtract_one_after_counting",
        "entry_shock_self_excluded": False,
        "cross_market_directed_neighbor_links": int(
            cross_market_directed_links
        ),
        "panel_rows_potentially_self_counted_as_prior_year_entry": int(
            self_contaminated_rows
        ),
        "legacy_choices_preserved": [
            "current rating is required for neighbor-pool membership",
            "legacy keyword category eligibility is required",
            "neighbors are queried globally within a fixed two-mile radius",
            "numeric prior-year entry shock retains focal-clinic self-counting",
            "density subtracts one after counting active clinics",
            "clinic-years run from entry year through 2025",
        ],
        "corrected_data_substitutions": [
            "stable clinic_key replaces row-order clinic_id",
            "corrected panel outcome replaces title-and-ZIP review linkage",
            "audited corrected replacement categories remain eligible",
        ],
        "conditional_fallbacks_used": [
            message
            for used, message in [
                (
                    entry_date_fallback_rows > 0,
                    "entry_date_proxy fills missing or invalid start_date rows",
                ),
            ]
            if used
        ],
        "alerts": [
            "legacy self-counting is intentionally retained",
            "results are a corrected-data legacy baseline, not final estimates",
        ],
    }
    return output, metadata


def fit_strict_legacy_two_mile_entity_fe(
    panel: pd.DataFrame,
) -> tuple[Any, dict[str, Any]]:
    """Fit the exact 009a final two-mile Entity FE formula."""

    try:
        from linearmodels.panel import PanelOLS
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    exposure = "log_lag_entry_shock_2mi_strict_009a"
    required = [
        "clinic_key",
        "year",
        "dynamic_rating",
        exposure,
        "log_votes_dynamic",
        "strict_009a_sample",
    ]
    missing = [column for column in required if column not in panel.columns]
    if missing:
        raise KeyError(f"Missing strict legacy regression columns: {missing}")

    model_data = panel.loc[panel["strict_009a_sample"].eq(True)].dropna(
        subset=required[:-1]
    ).copy()
    if model_data.duplicated(["clinic_key", "year"]).any():
        raise ValueError("Strict legacy sample has duplicate clinic-year rows")
    if model_data.empty:
        raise ValueError("Strict legacy regression sample is empty")

    model_data = model_data.set_index(["clinic_key", "year"]).sort_index()
    formula = (
        "dynamic_rating ~ log_lag_entry_shock_2mi_strict_009a "
        "+ log_votes_dynamic + EntityEffects"
    )
    model = PanelOLS.from_formula(
        formula,
        data=model_data,
        drop_absorbed=True,
    )
    result = model.fit(cov_type="clustered", cluster_entity=True)
    metadata = {
        "analysis_status": "strict_legacy_on_corrected_data_not_final",
        "specification_id": "009a_final_2mile_entity_fe_corrected_data",
        "legacy_source": "archive/2026/009a_2026-03-10_all_sanitized.ipynb",
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
        "legacy_defects_retained": [
            "numeric entry shock can count the focal clinic",
            "global neighbor query is retained",
            "log_votes_dynamic may be post-treatment",
        ],
        "corrected_data_substitutions": [
            "stable clinic_key replaces row-order clinic_id",
            "corrected panel outcome replaces title-and-ZIP review linkage",
        ],
    }
    return result, metadata
