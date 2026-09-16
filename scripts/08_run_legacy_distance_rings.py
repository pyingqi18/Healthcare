"""Run the legacy fixed distance-ring reproduction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.legacy_distance_rings import (
    build_legacy_distance_ring_exposures,
    fit_legacy_half_mile_entity_fe,
    fit_legacy_joint_distance_rings_entity_fe,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reproduce the legacy global 0-0.5, 0.5-2 and 2-5 mile rings."
        )
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--clinics", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def _coefficients(result: object, model_name: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "model": model_name,
            "term": result.params.index,
            "coefficient": result.params.to_numpy(),
            "standard_error": result.std_errors.to_numpy(),
            "t_statistic": result.tstats.to_numpy(),
            "p_value": result.pvalues.to_numpy(),
        }
    )


def main() -> None:
    args = parse_arguments()
    panel = pd.read_csv(args.panel, low_memory=False)
    clinics = pd.read_csv(args.clinics, low_memory=False)

    ring_panel, exposure_metadata = build_legacy_distance_ring_exposures(
        panel, clinics
    )
    joint_result, joint_metadata = (
        fit_legacy_joint_distance_rings_entity_fe(ring_panel)
    )
    half_result, half_metadata = fit_legacy_half_mile_entity_fe(ring_panel)

    args.output_directory.mkdir(parents=True, exist_ok=True)
    ring_panel.to_csv(
        args.output_directory / "legacy_distance_rings_panel.csv", index=False
    )
    for filename, metadata in [
        ("legacy_distance_rings_exposure_metadata.json", exposure_metadata),
        ("legacy_joint_rings_regression_metadata.json", joint_metadata),
        ("legacy_half_mile_regression_metadata.json", half_metadata),
    ]:
        (args.output_directory / filename).write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    (args.output_directory / "legacy_joint_rings_entity_fe.txt").write_text(
        str(joint_result.summary), encoding="utf-8"
    )
    (args.output_directory / "legacy_half_mile_entity_fe.txt").write_text(
        str(half_result.summary), encoding="utf-8"
    )
    coefficients = pd.concat(
        [
            _coefficients(joint_result, "joint_three_rings"),
            _coefficients(half_result, "standalone_half_mile"),
        ],
        ignore_index=True,
    )
    coefficients.to_csv(
        args.output_directory / "legacy_distance_rings_coefficients.csv",
        index=False,
    )

    print(json.dumps(exposure_metadata, indent=2, ensure_ascii=False))
    print(json.dumps(joint_metadata, indent=2, ensure_ascii=False))
    print(json.dumps(half_metadata, indent=2, ensure_ascii=False))
    print(coefficients.to_string(index=False))
    print(joint_result.summary)
    print(half_result.summary)


if __name__ == "__main__":
    main()
