"""Run the strict 009a two-mile baseline on corrected pipeline data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.strict_legacy_two_mile import (
    build_strict_legacy_two_mile_on_corrected_data,
    fit_strict_legacy_two_mile_entity_fe,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply the original 009a two-mile pool, exposure, and Entity FE "
            "choices to corrected pipeline data."
        )
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--clinics", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_arguments()
    panel = pd.read_csv(args.panel, low_memory=False)
    clinics = pd.read_csv(args.clinics, low_memory=False)
    output_directory = args.output_directory
    output_directory.mkdir(parents=True, exist_ok=True)

    strict_panel, exposure_metadata = (
        build_strict_legacy_two_mile_on_corrected_data(panel, clinics)
    )
    strict_panel.to_csv(
        output_directory / "strict_009a_2mile_panel.csv",
        index=False,
    )
    _write_json(
        output_directory / "strict_009a_2mile_exposure_metadata.json",
        exposure_metadata,
    )

    try:
        result, regression_metadata = (
            fit_strict_legacy_two_mile_entity_fe(strict_panel)
        )
    except Exception as exc:
        error = {
            "analysis_status": "strict_legacy_regression_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        _write_json(
            output_directory / "strict_009a_2mile_regression_error.json",
            error,
        )
        print(json.dumps(exposure_metadata, indent=2, ensure_ascii=False))
        print(json.dumps(error, indent=2, ensure_ascii=False))
        raise

    _write_json(
        output_directory / "strict_009a_2mile_regression_metadata.json",
        regression_metadata,
    )
    (output_directory / "strict_009a_2mile_entity_fe.txt").write_text(
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
        output_directory / "strict_009a_2mile_coefficients.csv",
        index=False,
    )

    print(json.dumps(exposure_metadata, indent=2, ensure_ascii=False))
    print(json.dumps(regression_metadata, indent=2, ensure_ascii=False))
    print(result.summary)


if __name__ == "__main__":
    main()
