"""Build and estimate the legacy fixed two-mile reproduction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.legacy_two_mile import (
    build_legacy_exact_two_mile_exposures,
    fit_legacy_two_mile_entity_fe,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reproduce the legacy global two-mile exposure and entity-FE model. "
            "Outputs are diagnostic and not final results."
        )
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--clinics", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    panel = pd.read_csv(args.panel, low_memory=False)
    clinics = pd.read_csv(args.clinics, low_memory=False)

    exposed_panel, exposure_metadata = (
        build_legacy_exact_two_mile_exposures(panel, clinics)
    )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    exposed_panel.to_csv(
        args.output_directory / "legacy_2mile_panel.csv",
        index=False,
    )
    (args.output_directory / "legacy_2mile_exposure_metadata.json").write_text(
        json.dumps(exposure_metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    try:
        result, regression_metadata = fit_legacy_two_mile_entity_fe(
            exposed_panel
        )
    except Exception as exc:
        error = {
            "analysis_status": "legacy_reproduction_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        (args.output_directory / "legacy_2mile_regression_error.json").write_text(
            json.dumps(error, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(json.dumps(exposure_metadata, indent=2, ensure_ascii=False))
        print(json.dumps(error, indent=2, ensure_ascii=False))
        raise

    (args.output_directory / "legacy_2mile_regression_metadata.json").write_text(
        json.dumps(regression_metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (args.output_directory / "legacy_2mile_entity_fe.txt").write_text(
        str(result.summary), encoding="utf-8"
    )
    coefficients = pd.DataFrame(
        {
            "term": result.params.index,
            "coefficient": result.params.to_numpy(),
            "standard_error": result.std_errors.to_numpy(),
            "t_statistic": result.tstats.to_numpy(),
            "p_value": result.pvalues.to_numpy(),
        }
    )
    coefficients.to_csv(
        args.output_directory / "legacy_2mile_coefficients.csv",
        index=False,
    )

    print(json.dumps(exposure_metadata, indent=2, ensure_ascii=False))
    print(json.dumps(regression_metadata, indent=2, ensure_ascii=False))
    print(result.summary)


if __name__ == "__main__":
    main()
