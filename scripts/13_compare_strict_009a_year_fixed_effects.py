"""Compare strict self-excluded Entity FE and Entity plus year FE."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.strict_two_mile_variants import (
    CORRECTED_LOG,
    fit_strict_009a_self_excluded_entity_fe,
    fit_strict_009a_self_excluded_entity_year_fe,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Keep the strict self-excluded exposure and sample fixed while "
            "adding common year fixed effects."
        )
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _coefficient_values(
    result: object, prefix: str
) -> dict[str, float]:
    return {
        f"{prefix}_coefficient": float(result.params[CORRECTED_LOG]),
        f"{prefix}_standard_error": float(result.std_errors[CORRECTED_LOG]),
        f"{prefix}_t_statistic": float(result.tstats[CORRECTED_LOG]),
        f"{prefix}_p_value": float(result.pvalues[CORRECTED_LOG]),
        f"{prefix}_within_r_squared": float(result.rsquared_within),
    }


def main() -> None:
    args = parse_arguments()
    panel = pd.read_csv(args.panel, low_memory=False)

    entity_result, entity_metadata = (
        fit_strict_009a_self_excluded_entity_fe(panel)
    )
    year_result, year_metadata = (
        fit_strict_009a_self_excluded_entity_year_fe(panel)
    )

    for field in ("sample_rows", "sample_clinics"):
        if entity_metadata[field] != year_metadata[field]:
            raise ValueError(
                f"Entity FE and Entity plus year FE samples differ in {field}"
            )

    comparison = {
        "term": "strict_009a_self_excluded_two_mile_entry_shock",
        "sample_rows": year_metadata["sample_rows"],
        "sample_clinics": year_metadata["sample_clinics"],
        "year_count": year_metadata["year_count"],
        **_coefficient_values(entity_result, "entity_fe"),
        **_coefficient_values(year_result, "entity_year_fe"),
    }
    comparison["coefficient_difference"] = (
        comparison["entity_year_fe_coefficient"]
        - comparison["entity_fe_coefficient"]
    )
    entity_coefficient = comparison["entity_fe_coefficient"]
    comparison["coefficient_percent_change"] = (
        comparison["coefficient_difference"] / entity_coefficient * 100
        if entity_coefficient != 0
        else float("nan")
    )

    output_directory = args.output_directory
    output_directory.mkdir(parents=True, exist_ok=True)
    _write_json(
        output_directory / "strict_009a_entity_year_fe_metadata.json",
        year_metadata,
    )
    (output_directory / "strict_009a_entity_year_fe.txt").write_text(
        str(year_result.summary), encoding="utf-8"
    )
    pd.DataFrame([comparison]).to_csv(
        output_directory / "strict_009a_entity_vs_entity_year_fe.csv",
        index=False,
    )

    print(json.dumps(year_metadata, indent=2, ensure_ascii=False))
    print(pd.DataFrame([comparison]).to_string(index=False))
    print(year_result.summary)


if __name__ == "__main__":
    main()
