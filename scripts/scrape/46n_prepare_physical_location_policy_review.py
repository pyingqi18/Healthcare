"""Prepare one consolidated policy review for stage 46m location blocks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.physical_location_policy_review import (
    prepare_physical_location_policy_review,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_context_arguments(parser)
    parser.add_argument("--block-triage", type=Path, default=None)
    parser.add_argument("--block-profiles", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "block_triage": (
                "interim",
                "profile_eligibility_final_application/physical_location_block_triage.csv",
            ),
            "block_profiles": (
                "interim",
                "profile_eligibility_final_application/physical_location_block_profiles.csv",
            ),
            "output_directory": (
                "interim",
                "physical_location_policy_review",
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
    inputs = [args.block_triage, args.block_profiles]
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing location-policy inputs: " + ", ".join(missing))
    output_paths = {
        "policy_decisions": args.output_directory
        / "physical_location_policy_decisions.csv",
        "manual_review_queue": args.output_directory
        / "physical_location_manual_review_queue.csv",
        "manual_review_profiles": args.output_directory
        / "physical_location_manual_review_profiles.csv",
    }
    summary_path = (
        args.output_directory / "physical_location_policy_prepare_summary.json"
    )
    _guard([*output_paths.values(), summary_path], args.overwrite)
    frames, summary = prepare_physical_location_policy_review(
        _read(args.block_triage), _read(args.block_profiles)
    )
    for key, frame in frames.items():
        _write_csv(frame, output_paths[key])
    summary["input_lineage"] = {
        "block_triage": str(args.block_triage),
        "block_profiles": str(args.block_profiles),
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
