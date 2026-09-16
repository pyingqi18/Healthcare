"""Compare year and market-year effects for the corrected two-mile model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.two_mile_variants import (
    fit_self_excluded_two_mile_entity_market_year_fe,
    fit_self_excluded_two_mile_entity_time_fe,
)


EXPOSURE = "log_lag_entry_shock_2mi_excl_self"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Hold the self-excluded two-mile exposure fixed and compare "
            "year effects with search-location-by-year effects."
        )
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def _statistics(result: object, prefix: str) -> dict[str, float]:
    return {
        f"{prefix}_coefficient": float(result.params[EXPOSURE]),
        f"{prefix}_standard_error": float(result.std_errors[EXPOSURE]),
        f"{prefix}_t_statistic": float(result.tstats[EXPOSURE]),
        f"{prefix}_p_value": float(result.pvalues[EXPOSURE]),
        f"{prefix}_within_r_squared": float(result.rsquared_within),
    }


def main() -> None:
    args = parse_arguments()
    panel = pd.read_csv(args.panel, low_memory=False)

    market_available = panel["search_location"].notna() & panel[
        "search_location"
    ].astype("string").str.strip().ne("")
    comparison_panel = panel.loc[market_available].copy()

    entity_year_result, entity_year_metadata = (
        fit_self_excluded_two_mile_entity_time_fe(comparison_panel)
    )
    market_year_result, market_year_metadata = (
        fit_self_excluded_two_mile_entity_market_year_fe(comparison_panel)
    )

    if entity_year_metadata["sample_rows"] != market_year_metadata["sample_rows"]:
        raise ValueError("Year and market-year models use different rows")
    if (
        entity_year_metadata["sample_clinics"]
        != market_year_metadata["sample_clinics"]
    ):
        raise ValueError("Year and market-year models use different clinics")

    comparison = {
        "term": "self_excluded_two_mile_prior_year_entry_shock",
        "sample_rows": entity_year_metadata["sample_rows"],
        "sample_clinics": entity_year_metadata["sample_clinics"],
        "market_count": market_year_metadata["market_count"],
        **_statistics(entity_year_result, "entity_year_fe"),
        **_statistics(market_year_result, "entity_market_year_fe"),
    }
    comparison["coefficient_difference"] = (
        comparison["entity_market_year_fe_coefficient"]
        - comparison["entity_year_fe_coefficient"]
    )
    baseline = comparison["entity_year_fe_coefficient"]
    comparison["coefficient_percent_change"] = (
        comparison["coefficient_difference"] / baseline * 100
        if baseline != 0
        else float("nan")
    )

    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / "entity_market_year_fe_metadata.json").write_text(
        json.dumps(market_year_metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (args.output_directory / "self_excluded_2mile_market_year_fe.txt").write_text(
        str(market_year_result.summary), encoding="utf-8"
    )
    pd.DataFrame([comparison]).to_csv(
        args.output_directory / "entity_year_vs_market_year_fe.csv",
        index=False,
    )

    print(json.dumps(market_year_metadata, indent=2, ensure_ascii=False))
    print(pd.DataFrame([comparison]).to_string(index=False))
    print(market_year_result.summary)


if __name__ == "__main__":
    main()
