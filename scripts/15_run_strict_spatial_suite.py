"""Run all remaining strict 009a spatial methods in one command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.strict_spatial_suite import (
    FIXED_EFFECT_SPECS,
    MODEL_EXPOSURES,
    build_strict_spatial_suite_exposures,
    fit_strict_spatial_model,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build strict gravity, KNN, ring, and half-mile exposures and run "
            "Entity, Entity plus Year, and Entity plus Market-Year models."
        )
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--clinics", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_arguments()
    panel = pd.read_csv(args.panel, low_memory=False)
    clinics = pd.read_csv(args.clinics, low_memory=False)
    exposed_panel, exposure_metadata = build_strict_spatial_suite_exposures(
        panel, clinics
    )

    coefficient_rows: list[dict[str, object]] = []
    regression_metadata: list[dict[str, Any]] = []
    summaries: list[str] = []
    reference_sample: tuple[int, int, int, int] | None = None
    for method in MODEL_EXPOSURES:
        for fixed_effects in FIXED_EFFECT_SPECS:
            result, metadata = fit_strict_spatial_model(
                exposed_panel,
                method=method,
                fixed_effects=fixed_effects,
            )
            sample_signature = (
                metadata["sample_rows"],
                metadata["sample_clinics"],
                metadata["minimum_year"],
                metadata["maximum_year"],
            )
            if reference_sample is None:
                reference_sample = sample_signature
            elif sample_signature != reference_sample:
                raise ValueError(
                    "Strict spatial models do not use an identical sample"
                )
            regression_metadata.append(metadata)
            summaries.append(
                f"===== {metadata['specification_id']} =====\n{result.summary}\n"
            )
            for term in result.params.index:
                coefficient_rows.append(
                    {
                        "method": method,
                        "fixed_effects": fixed_effects,
                        "term": term,
                        "coefficient": float(result.params[term]),
                        "standard_error": float(result.std_errors[term]),
                        "t_statistic": float(result.tstats[term]),
                        "p_value": float(result.pvalues[term]),
                        "sample_rows": metadata["sample_rows"],
                        "sample_clinics": metadata["sample_clinics"],
                    }
                )

    output_directory = args.output_directory
    output_directory.mkdir(parents=True, exist_ok=True)
    exposed_panel.to_csv(
        output_directory / "strict_spatial_suite_panel.csv", index=False
    )
    _write_json(
        output_directory / "strict_spatial_suite_metadata.json",
        exposure_metadata,
    )
    _write_json(
        output_directory / "strict_spatial_regression_metadata.json",
        regression_metadata,
    )
    pd.DataFrame(coefficient_rows).to_csv(
        output_directory / "strict_spatial_coefficients.csv", index=False
    )
    (output_directory / "strict_spatial_model_summaries.txt").write_text(
        "\n".join(summaries), encoding="utf-8"
    )

    print(json.dumps(exposure_metadata, indent=2, ensure_ascii=False))
    print(pd.DataFrame(coefficient_rows).to_string(index=False))


if __name__ == "__main__":
    main()
