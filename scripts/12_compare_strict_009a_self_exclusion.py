"""Compare frozen strict 009a and same-sample self-excluded estimates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.strict_legacy_two_mile import (
    fit_strict_legacy_two_mile_entity_fe,
)
from medical_ratings.strict_two_mile_variants import (
    BASELINE_LOG,
    CORRECTED_LOG,
    build_strict_009a_self_excluded_exposure,
    fit_strict_009a_self_excluded_entity_fe,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Keep the frozen strict 009a sample and model fixed while "
            "excluding the focal clinic from its own entry shock."
        )
    )
    parser.add_argument("--strict-panel", type=Path, required=True)
    parser.add_argument("--clinics", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _coefficient_values(
    result: object, exposure: str, prefix: str
) -> dict[str, float]:
    return {
        f"{prefix}_coefficient": float(result.params[exposure]),
        f"{prefix}_standard_error": float(result.std_errors[exposure]),
        f"{prefix}_t_statistic": float(result.tstats[exposure]),
        f"{prefix}_p_value": float(result.pvalues[exposure]),
    }


def main() -> None:
    args = parse_arguments()
    strict_panel = pd.read_csv(args.strict_panel, low_memory=False)
    clinics = pd.read_csv(args.clinics, low_memory=False)

    variant_panel, exposure_metadata = (
        build_strict_009a_self_excluded_exposure(strict_panel, clinics)
    )
    baseline_result, baseline_metadata = (
        fit_strict_legacy_two_mile_entity_fe(variant_panel)
    )
    variant_result, variant_metadata = (
        fit_strict_009a_self_excluded_entity_fe(variant_panel)
    )

    for field in ("sample_rows", "sample_clinics"):
        if baseline_metadata[field] != variant_metadata[field]:
            raise ValueError(
                f"Strict baseline and self-excluded samples differ in {field}"
            )

    comparison = {
        "term": "strict_009a_two_mile_prior_year_entry_shock",
        "sample_rows": variant_metadata["sample_rows"],
        "sample_clinics": variant_metadata["sample_clinics"],
        **_coefficient_values(
            baseline_result, BASELINE_LOG, "strict_legacy"
        ),
        **_coefficient_values(
            variant_result, CORRECTED_LOG, "self_excluded"
        ),
    }
    comparison["coefficient_difference"] = (
        comparison["self_excluded_coefficient"]
        - comparison["strict_legacy_coefficient"]
    )
    baseline_coefficient = comparison["strict_legacy_coefficient"]
    comparison["coefficient_percent_change"] = (
        comparison["coefficient_difference"] / baseline_coefficient * 100
        if baseline_coefficient != 0
        else float("nan")
    )

    output_directory = args.output_directory
    output_directory.mkdir(parents=True, exist_ok=True)
    variant_panel.to_csv(
        output_directory / "strict_009a_self_excluded_2mile_panel.csv",
        index=False,
    )
    _write_json(
        output_directory
        / "strict_009a_self_excluded_exposure_metadata.json",
        exposure_metadata,
    )
    _write_json(
        output_directory
        / "strict_009a_self_excluded_regression_metadata.json",
        variant_metadata,
    )
    (output_directory / "strict_009a_self_excluded_entity_fe.txt").write_text(
        str(variant_result.summary), encoding="utf-8"
    )
    pd.DataFrame([comparison]).to_csv(
        output_directory / "strict_009a_legacy_vs_self_excluded.csv",
        index=False,
    )

    print(json.dumps(exposure_metadata, indent=2, ensure_ascii=False))
    print(json.dumps(variant_metadata, indent=2, ensure_ascii=False))
    print(pd.DataFrame([comparison]).to_string(index=False))
    print(variant_result.summary)


if __name__ == "__main__":
    main()
