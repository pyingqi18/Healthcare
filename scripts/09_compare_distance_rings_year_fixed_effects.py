"""Compare legacy distance-ring models before and after adding year effects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.distance_ring_variants import (
    fit_half_mile_entity_year_fe,
    fit_joint_distance_rings_entity_year_fe,
)
from medical_ratings.legacy_distance_rings import (
    fit_legacy_half_mile_entity_fe,
    fit_legacy_joint_distance_rings_entity_fe,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Hold the legacy distance-ring exposures and samples fixed while "
            "adding common year fixed effects."
        )
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def _comparison_rows(
    *,
    model_name: str,
    entity_result: object,
    entity_year_result: object,
) -> list[dict[str, object]]:
    rows = []
    for term in entity_result.params.index:
        if term not in entity_year_result.params.index:
            continue
        entity_coefficient = float(entity_result.params[term])
        entity_year_coefficient = float(entity_year_result.params[term])
        difference = entity_year_coefficient - entity_coefficient
        percent_change = None
        if entity_coefficient != 0:
            percent_change = difference / entity_coefficient * 100
        rows.append(
            {
                "model": model_name,
                "term": term,
                "entity_fe_coefficient": entity_coefficient,
                "entity_fe_standard_error": float(
                    entity_result.std_errors[term]
                ),
                "entity_fe_p_value": float(entity_result.pvalues[term]),
                "entity_year_fe_coefficient": entity_year_coefficient,
                "entity_year_fe_standard_error": float(
                    entity_year_result.std_errors[term]
                ),
                "entity_year_fe_p_value": float(
                    entity_year_result.pvalues[term]
                ),
                "coefficient_difference": difference,
                "coefficient_percent_change": percent_change,
            }
        )
    return rows


def _require_same_sample(
    legacy_metadata: dict[str, object],
    variant_metadata: dict[str, object],
    model_name: str,
) -> None:
    for field in ("sample_rows", "sample_clinics", "minimum_year", "maximum_year"):
        if legacy_metadata[field] != variant_metadata[field]:
            raise ValueError(
                f"{model_name} fixed-effects models differ on {field}"
            )


def main() -> None:
    args = parse_arguments()
    panel = pd.read_csv(args.panel, low_memory=False)

    legacy_joint, legacy_joint_metadata = (
        fit_legacy_joint_distance_rings_entity_fe(panel)
    )
    year_joint, year_joint_metadata = (
        fit_joint_distance_rings_entity_year_fe(panel)
    )
    legacy_half, legacy_half_metadata = fit_legacy_half_mile_entity_fe(panel)
    year_half, year_half_metadata = fit_half_mile_entity_year_fe(panel)

    _require_same_sample(
        legacy_joint_metadata, year_joint_metadata, "joint distance-ring"
    )
    _require_same_sample(
        legacy_half_metadata, year_half_metadata, "standalone half-mile"
    )

    comparison = pd.DataFrame(
        _comparison_rows(
            model_name="joint_three_rings",
            entity_result=legacy_joint,
            entity_year_result=year_joint,
        )
        + _comparison_rows(
            model_name="standalone_half_mile",
            entity_result=legacy_half,
            entity_year_result=year_half,
        )
    )

    args.output_directory.mkdir(parents=True, exist_ok=True)
    for filename, metadata in (
        ("joint_rings_entity_year_fe_metadata.json", year_joint_metadata),
        ("half_mile_entity_year_fe_metadata.json", year_half_metadata),
    ):
        (args.output_directory / filename).write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    (args.output_directory / "joint_rings_entity_year_fe.txt").write_text(
        str(year_joint.summary), encoding="utf-8"
    )
    (args.output_directory / "half_mile_entity_year_fe.txt").write_text(
        str(year_half.summary), encoding="utf-8"
    )
    comparison.to_csv(
        args.output_directory / "distance_rings_entity_vs_entity_year_fe.csv",
        index=False,
    )

    print(json.dumps(year_joint_metadata, indent=2, ensure_ascii=False))
    print(json.dumps(year_half_metadata, indent=2, ensure_ascii=False))
    print(comparison.to_string(index=False))
    print(year_joint.summary)
    print(year_half.summary)


if __name__ == "__main__":
    main()
