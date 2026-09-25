"""Build tables, figures, and a Markdown report for legacy regressions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from medical_ratings.identifiers import normalize_zip


SIZE_ORDER = ["Small", "Mid_Size", "Large"]
STATE_ORDER = ["NY", "CA", "GA"]
SIZE_LABELS = {
    "Small": "Small town",
    "Mid_Size": "Mid-size city",
    "Large": "Large city",
}
ENTRY_TERMS = (
    "entry_shock",
    "lag_entry_shock",
    "log_shock",
    "gravity_shock",
    "dist_nearest_shock",
)
STAR_COLUMNS = [f"rating_{value}_star" for value in range(1, 6)]


def _require(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = columns - set(frame.columns)
    if missing:
        raise KeyError(f"{label} is missing: {sorted(missing)}")


def _clean(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip()


def _boolean(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False).astype(bool)
    return values.astype("string").str.strip().str.casefold().isin({"true", "1"})


def _zip_market_lookup(
    regions: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for market, details in regions.items():
        values = details.get("zip_values", [])
        ranges = details.get("zip_ranges", [])
        for value in values:
            zip_code = f"{int(value):05d}"
            if zip_code in lookup and lookup[zip_code] != market:
                raise ValueError(f"ZIP belongs to multiple markets: {zip_code}")
            lookup[zip_code] = market
        for lower, upper in ranges:
            for value in range(int(lower), int(upper) + 1):
                zip_code = f"{value:05d}"
                if zip_code in lookup and lookup[zip_code] != market:
                    raise ValueError(f"ZIP belongs to multiple markets: {zip_code}")
                lookup[zip_code] = market
    return lookup


def _first_nonblank(frame: pd.DataFrame, columns: Sequence[str]) -> pd.Series:
    output = pd.Series(pd.NA, index=frame.index, dtype="string")
    for column in columns:
        if column not in frame.columns:
            continue
        values = _clean(frame[column])
        usable = values.notna() & values.ne("")
        output = output.mask(output.isna() & usable, values)
    return output


def _market_metadata(
    regions: Mapping[str, Mapping[str, Any]],
) -> pd.DataFrame:
    records = []
    for market, details in regions.items():
        records.append(
            {
                "market": str(market),
                "state": str(details.get("state", "")),
                "city_size": str(details.get("size", "")),
            }
        )
    metadata = pd.DataFrame.from_records(records)
    if metadata["market"].duplicated().any():
        raise ValueError("Region configuration contains duplicate markets")
    return metadata


def _category_family(
    clinics: pd.DataFrame,
    category_mapping: pd.DataFrame | None,
) -> pd.Series:
    category = _clean(clinics["category"]) if "category" in clinics else pd.Series(
        "Unclassified", index=clinics.index, dtype="string"
    )
    direct = {
        "keywords_General_Dentist": "General dentist",
        "keywords_Special_Dentist": "Specialist dentist",
        "keywords_Surgery_Dentist": "Oral surgery",
    }
    family = category.map(direct).astype("string")
    if category_mapping is not None and not category_mapping.empty:
        group_column = next(
            (
                column
                for column in ("legacy_category_group", "category_group")
                if column in category_mapping.columns
            ),
            None,
        )
        if group_column is None:
            raise KeyError(
                "Category mapping is missing legacy_category_group or category_group"
            )
        _require(category_mapping, {"category"}, "Category mapping")
        mapping = (
            category_mapping.drop_duplicates("category")
            .set_index("category")[group_column]
            .map(
                {
                    "keywords_General_Dentist": "General dentist",
                    "keywords_Special_Dentist": "Specialist dentist",
                    "keywords_Surgery_Dentist": "Oral surgery",
                }
            )
        )
        family = family.fillna(category.map(mapping))
    return family.fillna("Other audited dental")


def _rating_dispersion(clinics: pd.DataFrame) -> pd.Series:
    if not set(STAR_COLUMNS).issubset(clinics.columns):
        return pd.Series(np.nan, index=clinics.index, dtype="float64")
    counts = clinics[STAR_COLUMNS].apply(pd.to_numeric, errors="coerce").fillna(0)
    stars = np.arange(1.0, 6.0)
    total = counts.sum(axis=1).to_numpy(dtype=float)
    weighted_sum = counts.to_numpy(dtype=float) @ stars
    weighted_square_sum = counts.to_numpy(dtype=float) @ (stars**2)
    variance = np.full(len(clinics), np.nan, dtype=float)
    valid = total > 1
    variance[valid] = (
        weighted_square_sum[valid]
        - weighted_sum[valid] ** 2 / total[valid]
    ) / (total[valid] - 1)
    variance = np.maximum(variance, 0)
    return pd.Series(np.sqrt(variance), index=clinics.index)


def prepare_legacy_report_data(
    panel: pd.DataFrame,
    clinics: pd.DataFrame,
    regions: Mapping[str, Mapping[str, Any]],
    *,
    strict_panel: pd.DataFrame | None = None,
    category_mapping: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Prepare one clinic cross-section and one clinic-year analysis frame."""

    _require(panel, {"clinic_key", "year", "dynamic_rating"}, "Panel")
    _require(clinics, {"clinic_key", "rating_value", "zip"}, "Clinics")
    if panel.duplicated(["clinic_key", "year"]).any():
        raise ValueError("Panel contains duplicate clinic-year rows")
    if clinics["clinic_key"].duplicated().any():
        raise ValueError("Clinics contain duplicate clinic_key rows")

    zip_lookup = _zip_market_lookup(regions)
    metadata = _market_metadata(regions)
    clinic = clinics.copy()
    clinic["market"] = clinic["zip"].map(normalize_zip).map(zip_lookup).astype("string")
    fallback_market = _first_nonblank(clinic, ["mapped_location", "search_location"])
    clinic["market"] = clinic["market"].fillna(fallback_market)
    clinic["rating_value"] = pd.to_numeric(clinic["rating_value"], errors="coerce")
    clinic["category_family"] = _category_family(clinic, category_mapping)
    clinic["rating_dispersion"] = _rating_dispersion(clinic)

    panel_source = strict_panel.copy() if strict_panel is not None else panel.copy()
    _require(panel_source, {"clinic_key", "year", "dynamic_rating"}, "Report panel")
    if panel_source.duplicated(["clinic_key", "year"]).any():
        raise ValueError("Report panel contains duplicate clinic-year rows")
    if "strict_009a_sample" in panel_source.columns:
        panel_source = panel_source.loc[_boolean(panel_source["strict_009a_sample"])].copy()
    clinic_market = clinic.set_index("clinic_key")["market"]
    panel_source["market"] = panel_source["clinic_key"].map(clinic_market).astype(
        "string"
    )
    panel_source["market"] = panel_source["market"].fillna(
        _first_nonblank(
            panel_source, ["strict_market", "mapped_location", "search_location"]
        )
    )
    panel_source["year"] = pd.to_numeric(panel_source["year"], errors="coerce")
    panel_source["dynamic_rating"] = pd.to_numeric(
        panel_source["dynamic_rating"], errors="coerce"
    )

    strict_keys = set(panel_source["clinic_key"].dropna().astype(str))
    clinic["strict_panel_member"] = clinic["clinic_key"].astype(str).isin(strict_keys)
    clinic_analysis = clinic.loc[
        clinic["rating_value"].between(1, 5) & clinic["market"].notna()
    ].copy()
    if "spatial_analysis_eligible" in clinic_analysis.columns:
        clinic_analysis = clinic_analysis.loc[
            _boolean(clinic_analysis["spatial_analysis_eligible"])
        ].copy()
    panel_analysis = panel_source.loc[
        panel_source["dynamic_rating"].between(1, 5)
        & panel_source["market"].notna()
        & panel_source["year"].notna()
    ].copy()

    clinic_analysis = clinic_analysis.merge(metadata, on="market", how="left", validate="many_to_one")
    panel_analysis = panel_analysis.merge(metadata, on="market", how="left", validate="many_to_one")
    if clinic_analysis[["state", "city_size"]].isna().any().any():
        raise ValueError("Some clinic markets are absent from regions.yaml")
    if panel_analysis[["state", "city_size"]].isna().any().any():
        raise ValueError("Some panel markets are absent from regions.yaml")

    summary = {
        "clinic_rows_used": int(len(clinic_analysis)),
        "clinic_markets_used": int(clinic_analysis["market"].nunique()),
        "clinic_rows_in_strict_panel": int(
            clinic_analysis["strict_panel_member"].sum()
        ),
        "panel_rows_used": int(len(panel_analysis)),
        "panel_clinics_used": int(panel_analysis["clinic_key"].nunique()),
        "panel_minimum_year": int(panel_analysis["year"].min()),
        "panel_maximum_year": int(panel_analysis["year"].max()),
        "strict_panel_supplied": strict_panel is not None,
        "low_rating_threshold": 3.0,
        "rating_unit": "one clinic for cross-section and one clinic-year for panel trends",
    }
    return clinic_analysis, panel_analysis, summary


def _summarize_ratings(frame: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    work = frame.copy()
    work["low_rating"] = work["rating_value"].le(3)
    result = (
        work.groupby(groups, observed=True, dropna=False)
        .agg(
            clinic_count=("clinic_key", "nunique"),
            mean_rating=("rating_value", "mean"),
            median_rating=("rating_value", "median"),
            standard_deviation=("rating_value", "std"),
            q25_rating=("rating_value", lambda value: value.quantile(0.25)),
            q75_rating=("rating_value", lambda value: value.quantile(0.75)),
            low_rating_share=("low_rating", "mean"),
            mean_rating_dispersion=("rating_dispersion", "mean"),
        )
        .reset_index()
    )
    result["standard_error"] = result["standard_deviation"] / np.sqrt(
        result["clinic_count"].clip(lower=1)
    )
    result["ci95_lower"] = result["mean_rating"] - 1.96 * result["standard_error"]
    result["ci95_upper"] = result["mean_rating"] + 1.96 * result["standard_error"]
    return result


def build_descriptive_tables(
    clinics: pd.DataFrame,
    panel: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Build all descriptive tables used by the report and figures."""

    by_market = _summarize_ratings(clinics, ["state", "city_size", "market"])
    by_size = _summarize_ratings(clinics, ["city_size"])
    by_state = _summarize_ratings(clinics, ["state"])
    by_state_size = _summarize_ratings(clinics, ["state", "city_size"])
    by_category_size = _summarize_ratings(
        clinics, ["category_family", "city_size"]
    )
    panel_trend = (
        panel.groupby(["year", "city_size"], observed=True)
        .agg(
            clinic_year_rows=("clinic_key", "size"),
            clinic_count=("clinic_key", "nunique"),
            mean_dynamic_rating=("dynamic_rating", "mean"),
            median_dynamic_rating=("dynamic_rating", "median"),
            standard_deviation=("dynamic_rating", "std"),
        )
        .reset_index()
    )
    state_trend = (
        panel.groupby(["year", "state"], observed=True)
        .agg(
            clinic_year_rows=("clinic_key", "size"),
            clinic_count=("clinic_key", "nunique"),
            mean_dynamic_rating=("dynamic_rating", "mean"),
        )
        .reset_index()
    )
    market_year_counts = (
        panel.groupby(["market", "year"], observed=True)
        .agg(clinic_year_rows=("clinic_key", "size"))
        .reset_index()
    )
    return {
        "clinic_rating_by_market": by_market,
        "clinic_rating_by_size": by_size,
        "clinic_rating_by_state": by_state,
        "clinic_rating_by_state_size": by_state_size,
        "clinic_rating_by_category_size": by_category_size,
        "panel_rating_trend_by_size": panel_trend,
        "panel_rating_trend_by_state": state_trend,
        "panel_market_year_counts": market_year_counts,
    }


def _coefficient_rows(
    frame: pd.DataFrame,
    *,
    model_id: str,
    model_family: str,
    source_file: str,
    term_column: str = "term",
) -> pd.DataFrame:
    _require(
        frame,
        {term_column, "coefficient", "standard_error", "p_value"},
        source_file,
    )
    output = pd.DataFrame(
        {
            "model_id": model_id,
            "model_family": model_family,
            "term": frame[term_column].astype(str),
            "coefficient": pd.to_numeric(frame["coefficient"], errors="raise"),
            "standard_error": pd.to_numeric(
                frame["standard_error"], errors="raise"
            ),
            "p_value": pd.to_numeric(frame["p_value"], errors="raise"),
            "source_file": source_file,
        }
    )
    if "sample_rows" in frame:
        output["sample_rows"] = pd.to_numeric(frame["sample_rows"], errors="coerce")
    if "sample_clinics" in frame:
        output["sample_clinics"] = pd.to_numeric(
            frame["sample_clinics"], errors="coerce"
        )
    return output


def _wide_rows(
    frame: pd.DataFrame,
    *,
    prefix_models: Mapping[str, str],
    model_family: str,
    source_file: str,
) -> list[pd.DataFrame]:
    _require(frame, {"term"}, source_file)
    outputs = []
    for prefix, model_id in prefix_models.items():
        required = {
            f"{prefix}_coefficient",
            f"{prefix}_standard_error",
            f"{prefix}_p_value",
        }
        _require(frame, required, source_file)
        temp = pd.DataFrame(
            {
                "term": frame["term"].astype(str),
                "coefficient": frame[f"{prefix}_coefficient"],
                "standard_error": frame[f"{prefix}_standard_error"],
                "p_value": frame[f"{prefix}_p_value"],
            }
        )
        for column in ("sample_rows", "sample_clinics"):
            if column in frame:
                temp[column] = frame[column]
        outputs.append(
            _coefficient_rows(
                temp,
                model_id=model_id,
                model_family=model_family,
                source_file=source_file,
            )
        )
    return outputs


def collect_regression_coefficients(results_root: Path) -> tuple[pd.DataFrame, list[str]]:
    """Collect known legacy and strict regression outputs into one long table."""

    frames: list[pd.DataFrame] = []
    missing: list[str] = []

    def read(relative: str) -> pd.DataFrame | None:
        path = results_root / relative
        if not path.exists():
            missing.append(relative)
            return None
        return pd.read_csv(path, low_memory=False)

    basic_specs = [
        (
            "legacy_2mile/legacy_2mile_coefficients.csv",
            "compatible_2mile_entity",
            "compatible_2mile",
        ),
        (
            "strict_009a_2mile/strict_009a_2mile_coefficients.csv",
            "strict_2mile_legacy_entity",
            "strict_2mile",
        ),
    ]
    for relative, model_id, family in basic_specs:
        frame = read(relative)
        if frame is not None:
            frames.append(
                _coefficient_rows(
                    frame,
                    model_id=model_id,
                    model_family=family,
                    source_file=relative,
                )
            )

    comparison_specs = [
        (
            "self_excluded_2mile/legacy_vs_self_excluded_2mile.csv",
            {
                "legacy": "compatible_2mile_entity",
                "self_excluded": "compatible_2mile_self_excluded_entity",
            },
            "compatible_2mile",
        ),
        (
            "entity_year_fe/entity_vs_entity_year_fe.csv",
            {
                "entity_fe": "compatible_2mile_self_excluded_entity",
                "entity_year_fe": "compatible_2mile_self_excluded_entity_year",
            },
            "compatible_2mile",
        ),
        (
            "market_year_fe/entity_year_vs_market_year_fe.csv",
            {
                "entity_year_fe": "compatible_2mile_self_excluded_entity_year",
                "entity_market_year_fe": "compatible_2mile_self_excluded_market_year",
            },
            "compatible_2mile",
        ),
        (
            "strict_009a_self_excluded_2mile/strict_009a_legacy_vs_self_excluded.csv",
            {
                "strict_legacy": "strict_2mile_legacy_entity",
                "self_excluded": "strict_2mile_self_excluded_entity",
            },
            "strict_2mile",
        ),
        (
            "strict_009a_entity_year_fe/strict_009a_entity_vs_entity_year_fe.csv",
            {
                "entity_fe": "strict_2mile_self_excluded_entity",
                "entity_year_fe": "strict_2mile_self_excluded_entity_year",
            },
            "strict_2mile",
        ),
        (
            "strict_009a_market_year_fe/strict_009a_year_vs_market_year_fe.csv",
            {
                "entity_year_fe": "strict_2mile_self_excluded_entity_year",
                "entity_market_year_fe": "strict_2mile_self_excluded_market_year",
            },
            "strict_2mile",
        ),
    ]
    for relative, prefixes, family in comparison_specs:
        frame = read(relative)
        if frame is not None:
            frames.extend(
                _wide_rows(
                    frame,
                    prefix_models=prefixes,
                    model_family=family,
                    source_file=relative,
                )
            )

    ring_base = read("distance_rings/legacy_distance_rings_coefficients.csv")
    if ring_base is not None:
        _require(ring_base, {"model"}, "legacy distance rings")
        for model, group in ring_base.groupby("model", sort=True):
            frames.append(
                _coefficient_rows(
                    group,
                    model_id=f"legacy_{model}_entity",
                    model_family="distance_rings",
                    source_file="distance_rings/legacy_distance_rings_coefficients.csv",
                )
            )
    ring_comparisons = [
        (
            "distance_rings_year_fe/distance_rings_entity_vs_entity_year_fe.csv",
            "entity_year_fe",
            "entity_year",
        ),
        (
            "distance_rings_market_year_fe/distance_rings_year_vs_market_year_fe.csv",
            "entity_market_year_fe",
            "market_year",
        ),
    ]
    for relative, prefix, suffix in ring_comparisons:
        frame = read(relative)
        if frame is None:
            continue
        _require(frame, {"model"}, relative)
        for model, group in frame.groupby("model", sort=True):
            frames.extend(
                _wide_rows(
                    group,
                    prefix_models={prefix: f"legacy_{model}_{suffix}"},
                    model_family="distance_rings",
                    source_file=relative,
                )
            )

    spatial = read("strict_spatial_suite/strict_spatial_coefficients.csv")
    if spatial is not None:
        _require(spatial, {"method", "fixed_effects"}, "strict spatial coefficients")
        for (method, fixed_effects), group in spatial.groupby(
            ["method", "fixed_effects"], sort=True
        ):
            frames.append(
                _coefficient_rows(
                    group,
                    model_id=f"strict_{method}_{fixed_effects}",
                    model_family="strict_spatial_suite",
                    source_file="strict_spatial_suite/strict_spatial_coefficients.csv",
                )
            )

    if not frames:
        raise FileNotFoundError("No recognized regression coefficient files were found")
    coefficients = pd.concat(frames, ignore_index=True, sort=False)
    coefficients["ci95_lower"] = coefficients["coefficient"] - 1.96 * coefficients[
        "standard_error"
    ]
    coefficients["ci95_upper"] = coefficients["coefficient"] + 1.96 * coefficients[
        "standard_error"
    ]
    coefficients["statistically_significant_5pct"] = coefficients["p_value"].lt(0.05)
    coefficients = coefficients.drop_duplicates(
        ["model_id", "term"], keep="last"
    ).sort_values(["model_family", "model_id", "term"], ignore_index=True)
    return coefficients, missing


def _markdown_table(frame: pd.DataFrame, *, digits: int = 4) -> str:
    if frame.empty:
        return "No rows available."
    display = frame.copy()
    for column in display.select_dtypes(include=["number"]).columns:
        display[column] = display[column].map(
            lambda value: "" if pd.isna(value) else f"{value:.{digits}f}"
        )
    headers = [str(column) for column in display.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in display.itertuples(index=False, name=None):
        values = [str(value).replace("|", "\\|") for value in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _save_figure(fig: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    import matplotlib.pyplot as plt

    plt.close(fig)


def _forest_plot(
    frame: pd.DataFrame,
    *,
    label_column: str,
    title: str,
    path: Path,
) -> bool:
    if frame.empty:
        return False
    import matplotlib.pyplot as plt

    plot = frame.copy().reset_index(drop=True)
    height = max(4.5, 0.38 * len(plot) + 1.8)
    fig, ax = plt.subplots(figsize=(10, height))
    y = np.arange(len(plot))
    colors = np.where(plot["p_value"].lt(0.05), "#1f4e79", "#8c8c8c")
    ax.hlines(y, plot["ci95_lower"], plot["ci95_upper"], color=colors, linewidth=2)
    ax.scatter(plot["coefficient"], y, color=colors, s=42, zorder=3)
    ax.axvline(0, color="black", linewidth=1, linestyle="--")
    ax.set_yticks(y, plot[label_column])
    ax.invert_yaxis()
    ax.set_xlabel("Coefficient with 95% confidence interval")
    ax.set_title(title)
    ax.grid(axis="x", alpha=0.2)
    _save_figure(fig, path)
    return True


def generate_legacy_report_figures(
    clinics: pd.DataFrame,
    panel: pd.DataFrame,
    tables: Mapping[str, pd.DataFrame],
    coefficients: pd.DataFrame,
    output_directory: Path,
) -> list[str]:
    """Generate a fixed, non-duplicative set of descriptive and model figures."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid", context="notebook")
    figures = output_directory / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    market_order = (
        tables["clinic_rating_by_market"]
        .sort_values(
            ["state", "city_size", "market"],
            key=lambda values: values.map(
                {**{v: i for i, v in enumerate(STATE_ORDER)}, **{v: i for i, v in enumerate(SIZE_ORDER)}}
            ).fillna(999)
            if values.name in {"state", "city_size"}
            else values,
        )["market"]
        .tolist()
    )

    fig, ax = plt.subplots(figsize=(15, 6))
    sns.boxplot(data=clinics, x="market", y="rating_value", order=market_order, ax=ax, color="#9ecae1", fliersize=1.5)
    ax.set_ylim(1, 5.1)
    ax.set_xlabel("Market")
    ax.set_ylabel("Current Google rating")
    ax.set_title("Clinic rating distribution across the 15 markets")
    ax.tick_params(axis="x", rotation=55)
    name = "01_clinic_rating_by_market_boxplot.png"
    _save_figure(fig, figures / name)
    created.append(name)

    market_summary = tables["clinic_rating_by_market"].set_index("market").loc[market_order].reset_index()
    fig, ax = plt.subplots(figsize=(12, 7))
    y = np.arange(len(market_summary))
    ax.errorbar(
        market_summary["mean_rating"],
        y,
        xerr=[market_summary["mean_rating"] - market_summary["ci95_lower"], market_summary["ci95_upper"] - market_summary["mean_rating"]],
        fmt="o",
        color="#1f4e79",
        ecolor="#6baed6",
        capsize=3,
    )
    ax.set_yticks(y, market_summary["market"])
    ax.invert_yaxis()
    ax.set_xlim(1, 5.1)
    ax.set_xlabel("Mean current rating with 95% confidence interval")
    ax.set_title("Mean clinic rating by market")
    name = "02_clinic_mean_rating_by_market_ci.png"
    _save_figure(fig, figures / name)
    created.append(name)

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.boxplot(data=clinics, x="city_size", y="rating_value", order=SIZE_ORDER, ax=ax, color="#a1d99b")
    ax.set_xticks(
        ax.get_xticks(),
        labels=[SIZE_LABELS[value] for value in SIZE_ORDER],
    )
    ax.set_ylim(1, 5.1)
    ax.set_xlabel("Market size")
    ax.set_ylabel("Current Google rating")
    ax.set_title("Clinic rating by market size")
    name = "03_clinic_rating_by_city_size.png"
    _save_figure(fig, figures / name)
    created.append(name)

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.boxplot(data=clinics, x="state", y="rating_value", order=STATE_ORDER, ax=ax, color="#fdae6b")
    ax.set_ylim(1, 5.1)
    ax.set_xlabel("State")
    ax.set_ylabel("Current Google rating")
    ax.set_title("Clinic rating by state")
    name = "04_clinic_rating_by_state.png"
    _save_figure(fig, figures / name)
    created.append(name)

    category_size = tables["clinic_rating_by_category_size"].copy()
    fig, ax = plt.subplots(figsize=(11, 6))
    sns.barplot(
        data=category_size,
        x="category_family",
        y="mean_rating",
        hue="city_size",
        hue_order=SIZE_ORDER,
        ax=ax,
    )
    ax.set_ylim(max(1, category_size["mean_rating"].min() - 0.3), 5.05)
    ax.set_xlabel("Dental category family")
    ax.set_ylabel("Mean current rating")
    ax.set_title("Mean clinic rating by category and market size")
    ax.tick_params(axis="x", rotation=20)
    name = "05_rating_by_category_and_city_size.png"
    _save_figure(fig, figures / name)
    created.append(name)

    state_size = tables["clinic_rating_by_state_size"].copy()
    fig, ax = plt.subplots(figsize=(9, 6))
    sns.barplot(
        data=state_size,
        x="state",
        y="low_rating_share",
        hue="city_size",
        order=STATE_ORDER,
        hue_order=SIZE_ORDER,
        ax=ax,
    )
    ax.set_xlabel("State")
    ax.set_ylabel("Share of clinics with rating at or below 3")
    ax.set_title("Low-rating share by state and market size")
    name = "06_low_rating_share_by_state_and_size.png"
    _save_figure(fig, figures / name)
    created.append(name)

    trend = tables["panel_rating_trend_by_size"]
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.lineplot(data=trend, x="year", y="mean_dynamic_rating", hue="city_size", hue_order=SIZE_ORDER, marker="o", ax=ax)
    ax.set_xlabel("Year")
    ax.set_ylabel("Mean cumulative clinic rating")
    ax.set_title("Rating trend by market size in the strict panel")
    name = "07_panel_rating_trend_by_city_size.png"
    _save_figure(fig, figures / name)
    created.append(name)

    state_trend = tables["panel_rating_trend_by_state"]
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.lineplot(data=state_trend, x="year", y="mean_dynamic_rating", hue="state", hue_order=STATE_ORDER, marker="o", ax=ax)
    ax.set_xlabel("Year")
    ax.set_ylabel("Mean cumulative clinic rating")
    ax.set_title("Rating trend by state in the strict panel")
    name = "08_panel_rating_trend_by_state.png"
    _save_figure(fig, figures / name)
    created.append(name)

    heat = tables["panel_market_year_counts"].pivot(index="market", columns="year", values="clinic_year_rows").fillna(0)
    heat = heat.reindex([value for value in market_order if value in heat.index])
    fig, ax = plt.subplots(figsize=(13, 7))
    sns.heatmap(heat, cmap="Blues", ax=ax, cbar_kws={"label": "Clinic-year rows"})
    ax.set_xlabel("Year")
    ax.set_ylabel("Market")
    ax.set_title("Strict regression sample coverage by market and year")
    name = "09_panel_market_year_sample_heatmap.png"
    _save_figure(fig, figures / name)
    created.append(name)

    exposure_column = next(
        (
            column
            for column in [
                "lag_entry_shock_2mi_count_strict_009a_excl_self",
                "lag_entry_shock_2mi_count_strict_009a",
                "log_lag_entry_shock_2mi_excl_self",
                "log_lag_entry_shock_2mi",
            ]
            if column in panel.columns
        ),
        None,
    )
    if exposure_column is not None:
        entry_value = pd.to_numeric(panel[exposure_column], errors="coerce")
        panel_plot = panel.loc[entry_value.notna()].copy()
        panel_plot["entry_group"] = np.where(entry_value.loc[panel_plot.index].gt(0), "Prior-year entry", "No prior-year entry")
        fig, ax = plt.subplots(figsize=(9, 6))
        sns.histplot(
            data=panel_plot,
            x="dynamic_rating",
            hue="entry_group",
            bins=16,
            stat="density",
            common_norm=False,
            element="step",
            fill=False,
            ax=ax,
        )
        ax.set_xlim(1, 5.05)
        ax.set_xlabel("Cumulative clinic rating")
        ax.set_ylabel("Density")
        ax.set_title("Legacy competition-group rating distribution")
        name = "10_entry_group_rating_distribution.png"
        _save_figure(fig, figures / name)
        created.append(name)

        fig, ax = plt.subplots(figsize=(10, 6))
        sns.boxplot(data=panel_plot, x="year", y="dynamic_rating", hue="entry_group", showfliers=False, ax=ax)
        ax.set_xlabel("Year")
        ax.set_ylabel("Cumulative clinic rating")
        ax.set_title("Rating distribution by year and prior-year entry group")
        ax.tick_params(axis="x", rotation=45)
        name = "11_entry_group_rating_by_year.png"
        _save_figure(fig, figures / name)
        created.append(name)

    compatible = coefficients.loc[
        coefficients["model_family"].isin(["compatible_2mile", "strict_2mile"])
        & coefficients["term"].map(lambda value: any(token in value for token in ENTRY_TERMS))
    ].copy()
    compatible["plot_label"] = compatible["model_id"]
    name = "12_two_mile_fixed_effect_forest.png"
    if _forest_plot(
        compatible,
        label_column="plot_label",
        title="Two-mile entry-shock estimates across sample and fixed-effect choices",
        path=figures / name,
    ):
        created.append(name)

    rings = coefficients.loc[coefficients["model_family"].eq("distance_rings")].copy()
    rings = rings.loc[~rings["term"].str.contains("Intercept|votes", case=False, regex=True)]
    rings["plot_label"] = rings["model_id"] + " | " + rings["term"]
    name = "13_distance_ring_forest.png"
    if _forest_plot(
        rings,
        label_column="plot_label",
        title="Distance-ring entry and density estimates",
        path=figures / name,
    ):
        created.append(name)

    spatial = coefficients.loc[coefficients["model_family"].eq("strict_spatial_suite")].copy()
    spatial = spatial.loc[~spatial["term"].str.contains("Intercept|const|votes", case=False, regex=True)]
    spatial["plot_label"] = spatial["model_id"] + " | " + spatial["term"]
    name = "14_strict_spatial_method_forest.png"
    if _forest_plot(
        spatial,
        label_column="plot_label",
        title="Strict spatial-method estimates",
        path=figures / name,
    ):
        created.append(name)

    if clinics["rating_dispersion"].notna().any():
        fig, ax = plt.subplots(figsize=(15, 6))
        sns.boxplot(data=clinics, x="market", y="rating_dispersion", order=market_order, ax=ax, color="#bcbddc", fliersize=1.5)
        ax.set_xlabel("Market")
        ax.set_ylabel("Within-profile rating standard deviation")
        ax.set_title("Review-rating dispersion by market")
        ax.tick_params(axis="x", rotation=55)
        name = "15_rating_dispersion_by_market.png"
        _save_figure(fig, figures / name)
        created.append(name)

    grid = sns.FacetGrid(
        clinics,
        col="market",
        col_wrap=5,
        col_order=market_order,
        height=2.1,
        sharex=True,
        sharey=False,
    )
    grid.map_dataframe(sns.histplot, x="rating_value", bins=np.linspace(1, 5, 17), color="#3182bd")
    grid.set_axis_labels("Rating", "Clinics")
    grid.set(xlim=(1, 5.05))
    grid.fig.suptitle("Clinic rating histograms by market", y=1.02)
    name = "16_clinic_rating_histograms_by_market.png"
    _save_figure(grid.fig, figures / name)
    created.append(name)
    return created


def _coefficient_focus_table(coefficients: pd.DataFrame) -> pd.DataFrame:
    focus = coefficients.loc[
        ~coefficients["term"].str.contains("Intercept|const|votes", case=False, regex=True)
    ].copy()
    return focus.loc[
        :,
        [
            "model_id",
            "term",
            "coefficient",
            "standard_error",
            "p_value",
            "ci95_lower",
            "ci95_upper",
        ],
    ]


def write_legacy_regression_report(
    output_directory: Path,
    *,
    data_summary: Mapping[str, Any],
    tables: Mapping[str, pd.DataFrame],
    coefficients: pd.DataFrame,
    figures: Sequence[str],
    missing_regression_files: Sequence[str],
) -> Path:
    """Write one self-contained Markdown index for the generated outputs."""

    by_market = tables["clinic_rating_by_market"].sort_values("mean_rating")
    by_size = tables["clinic_rating_by_size"].copy()
    by_state = tables["clinic_rating_by_state"].copy()
    lowest = by_market.iloc[0]
    highest = by_market.iloc[-1]
    strict_models = coefficients.loc[
        coefficients["model_family"].eq("strict_2mile")
        & coefficients["term"].map(lambda value: any(token in value for token in ENTRY_TERMS))
    ].copy()
    strict_models = strict_models.sort_values("model_id")

    lines = [
        "# Legacy回归与评分图表报告",
        "",
        "## 状态与解释边界",
        "",
        "本报告汇总corrected_v1上的legacy复现和后续逐项比较。它不是full_rebuild最终因果报告。回归系数只能解释为冻结样本与规格下的条件相关；市场、州和城市规模图是描述统计，不能单独识别地域或城市规模的因果效应。",
        "",
        "## 分析样本",
        "",
        f"诊所横截面记录：{data_summary['clinic_rows_used']}",
        "",
        f"覆盖市场：{data_summary['clinic_markets_used']}",
        "",
        f"其中进入strict panel的诊所：{data_summary['clinic_rows_in_strict_panel']}",
        "",
        f"strict panel记录：{data_summary['panel_rows_used']}",
        "",
        f"strict panel诊所：{data_summary['panel_clinics_used']}",
        "",
        f"panel年份：{data_summary['panel_minimum_year']}至{data_summary['panel_maximum_year']}",
        "",
        "低评分定义：当前Google平均评分小于等于3.0。",
        "",
        "市场、州和城市规模横截面使用corrected_v1中有有效评分且空间合格的诊所；年度趋势和entry group图使用strict panel。因此描述样本与回归样本在报告中明确分开。",
        "",
        "## 描述统计",
        "",
        f"市场均值最低：{lowest['market']}，平均评分{lowest['mean_rating']:.3f}，诊所{int(lowest['clinic_count'])}家。",
        "",
        f"市场均值最高：{highest['market']}，平均评分{highest['mean_rating']:.3f}，诊所{int(highest['clinic_count'])}家。",
        "",
        "这些排名会受到诊所构成、profile选择、评论量、进入时间和部分小市场样本量影响，不能当作控制协变量后的地域效应。",
        "",
        "### 按城市规模",
        "",
        _markdown_table(by_size[["city_size", "clinic_count", "mean_rating", "median_rating", "low_rating_share"]]),
        "",
        "### 按州",
        "",
        _markdown_table(by_state[["state", "clinic_count", "mean_rating", "median_rating", "low_rating_share"]]),
        "",
        "### 按市场",
        "",
        _markdown_table(by_market[["state", "city_size", "market", "clinic_count", "mean_rating", "standard_deviation", "low_rating_share"]]),
        "",
        "## 回归结果比较",
        "",
        "核心比较是entry shock系数在更严格的样本恢复和更强时间控制下是否仍然存在。仅Entity FE利用同一家诊所随时间的变化，但没有控制共同年度冲击。加入Year FE后会吸收所有市场共同经历的年度变化。Market×Year FE进一步吸收每个ZIP市场自己的年度冲击，因此是当前legacy比较中最严格的时间控制。",
        "",
    ]
    if not strict_models.empty:
        lines.extend(
            [
                "### Strict 2-mile entry shock逐步比较",
                "",
                _markdown_table(
                    strict_models[["model_id", "coefficient", "standard_error", "p_value", "ci95_lower", "ci95_upper"]]
                ),
                "",
            ]
        )
    lines.extend(
        [
            "### 全部非控制变量系数",
            "",
            _markdown_table(_coefficient_focus_table(coefficients), digits=5),
            "",
            "## 图形",
            "",
        ]
    )
    for name in figures:
        title = name.removesuffix(".png").replace("_", " ")
        lines.extend([f"### {title}", "", f"![{title}](figures/{name})", ""])
    lines.extend(
        [
            "## Legacy notebook图形复现决定",
            "",
            "旧notebook对每个类别、州和城市分别循环生成箱线图、小提琴图、直方图和散点图，图很多但跨市场比较困难。本报告保留原本要回答的问题，改成统一坐标和固定数量的多市场图，不重复输出信息相同的图片。",
            "",
            "旧notebook曾把诊所平均评分小于等于1作为低评分定义。诊所层面的Google平均评分几乎不会落在这个区间，因此本报告改用小于等于3.0，并在表中保存明确分母。",
            "",
            "旧notebook的strong-entry图需要基于进入者质量构造的strong-entry变量。如果corrected strict panel没有该字段，本报告只复现可验证的上一年无进入与有进入比较，不凭空制造strong-entry分类。",
            "",
            "## 缺少的可选输入",
            "",
        ]
    )
    if missing_regression_files:
        lines.extend([f"缺少可选回归文件：`{value}`" for value in missing_regression_files])
    else:
        lines.append("已找到全部登记的回归系数文件。")
    report = output_directory / "legacy_regression_report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def build_legacy_regression_report(
    panel: pd.DataFrame,
    clinics: pd.DataFrame,
    regions: Mapping[str, Mapping[str, Any]],
    *,
    results_root: Path,
    output_directory: Path,
    strict_panel: pd.DataFrame | None = None,
    category_mapping: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Create all tables, figures, metadata, and the Markdown report."""

    clinic_data, panel_data, data_summary = prepare_legacy_report_data(
        panel,
        clinics,
        regions,
        strict_panel=strict_panel,
        category_mapping=category_mapping,
    )
    tables = build_descriptive_tables(clinic_data, panel_data)
    coefficients, missing = collect_regression_coefficients(results_root)
    output_directory.mkdir(parents=True, exist_ok=True)
    table_directory = output_directory / "tables"
    table_directory.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_csv(table_directory / f"{name}.csv", index=False)
    coefficients.to_csv(
        table_directory / "regression_coefficients_long.csv", index=False
    )
    figures = generate_legacy_report_figures(
        clinic_data, panel_data, tables, coefficients, output_directory
    )
    report = write_legacy_regression_report(
        output_directory,
        data_summary=data_summary,
        tables=tables,
        coefficients=coefficients,
        figures=figures,
        missing_regression_files=missing,
    )
    summary = {
        "analysis_status": "legacy_corrected_data_report_not_final",
        **data_summary,
        "regression_models_collected": int(coefficients["model_id"].nunique()),
        "regression_terms_collected": int(len(coefficients)),
        "figures_created": len(figures),
        "figure_files": figures,
        "tables_created": len(tables) + 1,
        "missing_optional_regression_files": list(missing),
        "report": str(report),
        "automatic_model_selection_performed": False,
        "regression_balltree_modified": False,
    }
    (output_directory / "legacy_regression_report_metadata.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary
