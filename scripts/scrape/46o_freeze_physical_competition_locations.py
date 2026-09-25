"""Freeze physical competition locations under main and sensitivity rules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.final_physical_location_freeze import (
    freeze_physical_competition_locations,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_context_arguments(parser)
    parser.add_argument("--location-blocks", type=Path, default=None)
    parser.add_argument("--policy-decisions", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "location_blocks": (
                "interim",
                "profile_eligibility_final_application/physical_location_review_blocks.csv",
            ),
            "policy_decisions": (
                "interim",
                "physical_location_policy_review/physical_location_policy_decisions.csv",
            ),
            "output_directory": (
                "interim",
                "physical_location_final_freeze",
            ),
        },
    )


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def _guard(paths: list[Path], overwrite: bool) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(existing) + ". Use --overwrite."
        )


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    inputs = [args.location_blocks, args.policy_decisions]
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing final-location inputs: " + ", ".join(missing))
    output_paths = {
        "crosswalk": args.output_directory
        / "outcome_profile_competition_location_crosswalk.csv",
        "main_locations": args.output_directory
        / "physical_competition_locations_final.csv",
        "sensitivity_locations": args.output_directory
        / "physical_competition_locations_address_merge_sensitivity.csv",
    }
    summary_path = args.output_directory / "physical_location_final_freeze_summary.json"
    _guard([*output_paths.values(), summary_path], args.overwrite)
    frames, summary = freeze_physical_competition_locations(
        _read(args.location_blocks), _read(args.policy_decisions)
    )
    for key, frame in frames.items():
        _write_csv(frame, output_paths[key])
    summary["input_lineage"] = {
        "location_blocks": str(args.location_blocks),
        "policy_decisions": str(args.policy_decisions),
    }
    summary["outputs"] = {
        **{key: str(path) for key, path in output_paths.items()},
        "summary": str(summary_path),
    }
    _write_json(summary, summary_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
