"""Compare ring models using common-year and market-year fixed effects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.distance_ring_variants import (
    fit_half_mile_entity_market_year_fe,
    fit_half_mile_entity_year_fe,
    fit_joint_distance_rings_entity_market_year_fe,
    fit_joint_distance_rings_entity_year_fe,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Hold distance-ring exposures and samples fixed while replacing "
            "common year effects with search-location-by-year effects."
        )
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def _comparison_rows(
    *,
    model_name: str,
    year_result: object,
    market_year_result: object,
) -> list[dict[str, object]]:
    rows = []
    for term in year_result.params.index:
        if term not in market_year_result.params.index:
            continue
        year_coefficient = float(year_result.params[term])
        market_year_coefficient = float(market_year_result.params[term])
        difference = market_year_coefficient - year_coefficient
        percent_change = None
        if year_coefficient != 0:
            percent_change = difference / year_coefficient * 100
        rows.append(
            {
                "model": model_name,
                "term": term,
                "entity_year_fe_coefficient": year_coefficient,
                "entity_year_fe_standard_error": float(
                    year_result.std_errors[term]
                ),
                "entity_year_fe_p_value": float(year_result.pvalues[term]),
                "entity_market_year_fe_coefficient": market_year_coefficient,
                "entity_market_year_fe_standard_error": float(
                    market_year_result.std_errors[term]
                ),
                "entity_market_year_fe_p_value": float(
                    market_year_result.pvalues[term]
                ),
                "coefficient_difference": difference,
                "coefficient_percent_change": percent_change,
            }
        )
    return rows


def _require_same_sample(
    year_metadata: dict[str, object],
    market_year_metadata: dict[str, object],
    model_name: str,
) -> None:
    for field in ("sample_rows", "sample_clinics", "minimum_year", "maximum_year"):
        if year_metadata[field] != market_year_metadata[field]:
            raise ValueError(f"{model_name} models differ on {field}")


def main() -> None:
    args = parse_arguments()
    panel = pd.read_csv(args.panel, low_memory=False)

    year_joint, year_joint_metadata = (
        fit_joint_distance_rings_entity_year_fe(panel)
    )
    market_joint, market_joint_metadata = (
        fit_joint_distance_rings_entity_market_year_fe(panel)
    )
    year_half, year_half_metadata = fit_half_mile_entity_year_fe(panel)
    market_half, market_half_metadata = (
        fit_half_mile_entity_market_year_fe(panel)
    )

    _require_same_sample(
        year_joint_metadata, market_joint_metadata, "joint distance-ring"
    )
    _require_same_sample(
        year_half_metadata, market_half_metadata, "standalone half-mile"
    )

    comparison = pd.DataFrame(
        _comparison_rows(
            model_name="joint_three_rings",
            year_result=year_joint,
            market_year_result=market_joint,
        )
        + _comparison_rows(
            model_name="standalone_half_mile",
            year_result=year_half,
            market_year_result=market_half,
        )
    )

    args.output_directory.mkdir(parents=True, exist_ok=True)
    for filename, metadata in (
        ("joint_rings_market_year_fe_metadata.json", market_joint_metadata),
        ("half_mile_market_year_fe_metadata.json", market_half_metadata),
    ):
        (args.output_directory / filename).write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    (args.output_directory / "joint_rings_market_year_fe.txt").write_text(
        str(market_joint.summary), encoding="utf-8"
    )
    (args.output_directory / "half_mile_market_year_fe.txt").write_text(
        str(market_half.summary), encoding="utf-8"
    )
    comparison.to_csv(
        args.output_directory / "distance_rings_year_vs_market_year_fe.csv",
        index=False,
    )

    print(json.dumps(market_joint_metadata, indent=2, ensure_ascii=False))
    print(json.dumps(market_half_metadata, indent=2, ensure_ascii=False))
    print(comparison.to_string(index=False))
    print(market_joint.summary)
    print(market_half.summary)


if __name__ == "__main__":
    main()
