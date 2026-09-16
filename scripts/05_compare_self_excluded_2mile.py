"""Compare exact legacy and self-excluded two-mile entry shocks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.legacy_two_mile import fit_legacy_two_mile_entity_fe
from medical_ratings.two_mile_variants import (
    build_self_excluded_two_mile_exposures,
    fit_self_excluded_two_mile_entity_fe,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Hold the legacy two-mile model fixed and remove only the focal "
            "clinic from its own prior-year entry shock."
        )
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--clinics", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def _coefficient_row(result: object, exposure: str, prefix: str) -> dict:
    return {
        f"{prefix}_coefficient": float(result.params[exposure]),
        f"{prefix}_standard_error": float(result.std_errors[exposure]),
        f"{prefix}_t_statistic": float(result.tstats[exposure]),
        f"{prefix}_p_value": float(result.pvalues[exposure]),
    }


def main() -> None:
    args = parse_arguments()
    panel = pd.read_csv(args.panel, low_memory=False)
    clinics = pd.read_csv(args.clinics, low_memory=False)

    exposed_panel, exposure_metadata = (
        build_self_excluded_two_mile_exposures(panel, clinics)
    )
    legacy_result, legacy_metadata = fit_legacy_two_mile_entity_fe(
        exposed_panel
    )
    corrected_result, corrected_metadata = (
        fit_self_excluded_two_mile_entity_fe(exposed_panel)
    )

    if legacy_metadata["sample_rows"] != corrected_metadata["sample_rows"]:
        raise ValueError("Legacy and corrected regressions use different rows")
    if legacy_metadata["sample_clinics"] != corrected_metadata["sample_clinics"]:
        raise ValueError("Legacy and corrected regressions use different clinics")

    args.output_directory.mkdir(parents=True, exist_ok=True)
    exposed_panel.to_csv(
        args.output_directory / "self_excluded_2mile_panel.csv", index=False
    )
    (args.output_directory / "self_excluded_2mile_exposure_metadata.json").write_text(
        json.dumps(exposure_metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (args.output_directory / "self_excluded_2mile_regression_metadata.json").write_text(
        json.dumps(corrected_metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (args.output_directory / "self_excluded_2mile_entity_fe.txt").write_text(
        str(corrected_result.summary), encoding="utf-8"
    )

    comparison = {
        "term": "two_mile_prior_year_entry_shock",
        **_coefficient_row(
            legacy_result, "log_lag_entry_shock_2mi", "legacy"
        ),
        **_coefficient_row(
            corrected_result,
            "log_lag_entry_shock_2mi_excl_self",
            "self_excluded",
        ),
    }
    comparison["coefficient_difference"] = (
        comparison["self_excluded_coefficient"]
        - comparison["legacy_coefficient"]
    )
    pd.DataFrame([comparison]).to_csv(
        args.output_directory / "legacy_vs_self_excluded_2mile.csv",
        index=False,
    )

    print(json.dumps(exposure_metadata, indent=2, ensure_ascii=False))
    print(json.dumps(corrected_metadata, indent=2, ensure_ascii=False))
    print(pd.DataFrame([comparison]).to_string(index=False))
    print(corrected_result.summary)


if __name__ == "__main__":
    main()
