"""Compare clinic-only and clinic-plus-year fixed effects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.two_mile_variants import (
    fit_self_excluded_two_mile_entity_fe,
    fit_self_excluded_two_mile_entity_time_fe,
)


EXPOSURE = "log_lag_entry_shock_2mi_excl_self"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Hold the self-excluded two-mile exposure and regression sample "
            "fixed while adding year fixed effects."
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

    entity_result, entity_metadata = fit_self_excluded_two_mile_entity_fe(
        panel
    )
    entity_year_result, entity_year_metadata = (
        fit_self_excluded_two_mile_entity_time_fe(panel)
    )

    if entity_metadata["sample_rows"] != entity_year_metadata["sample_rows"]:
        raise ValueError("Fixed-effects models use different rows")
    if (
        entity_metadata["sample_clinics"]
        != entity_year_metadata["sample_clinics"]
    ):
        raise ValueError("Fixed-effects models use different clinics")

    comparison = {
        "term": "self_excluded_two_mile_prior_year_entry_shock",
        "sample_rows": entity_metadata["sample_rows"],
        "sample_clinics": entity_metadata["sample_clinics"],
        **_statistics(entity_result, "entity_fe"),
        **_statistics(entity_year_result, "entity_year_fe"),
    }
    comparison["coefficient_difference"] = (
        comparison["entity_year_fe_coefficient"]
        - comparison["entity_fe_coefficient"]
    )
    comparison["coefficient_percent_change"] = (
        comparison["coefficient_difference"]
        / comparison["entity_fe_coefficient"]
        * 100
    )

    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / "entity_year_fe_metadata.json").write_text(
        json.dumps(entity_year_metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (args.output_directory / "self_excluded_2mile_entity_year_fe.txt").write_text(
        str(entity_year_result.summary), encoding="utf-8"
    )
    pd.DataFrame([comparison]).to_csv(
        args.output_directory / "entity_vs_entity_year_fe.csv", index=False
    )

    print(json.dumps(entity_year_metadata, indent=2, ensure_ascii=False))
    print(pd.DataFrame([comparison]).to_string(index=False))
    print(entity_year_result.summary)


if __name__ == "__main__":
    main()
