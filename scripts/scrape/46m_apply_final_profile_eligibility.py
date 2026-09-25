"""Apply the 450-profile freeze and prepare physical-location review blocks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.profile_eligibility_final_application import (
    apply_final_verified_freeze,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_context_arguments(parser)
    parser.add_argument("--inventory", type=Path, default=None)
    parser.add_argument("--decision-template", type=Path, default=None)
    parser.add_argument("--carry-forward-anchors", type=Path, default=None)
    parser.add_argument(
        "--verified-before",
        type=Path,
        default=Path("config/profile_eligibility_verified_decisions_20260925.csv"),
    )
    parser.add_argument("--verified-additions", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "inventory": (
                "interim",
                "cross_source_profile_location_review/"
                "unified_cross_source_profile_inventory.csv",
            ),
            "decision_template": (
                "interim",
                "cross_source_profile_location_review/"
                "profile_eligibility_decisions.csv",
            ),
            "carry_forward_anchors": (
                "interim",
                "cross_source_profile_location_review/"
                "legacy_carry_forward_location_anchors.csv",
            ),
            "verified_additions": (
                "interim",
                "profile_eligibility_completion/remaining_profile_verified_additions.csv",
            ),
            "output_directory": (
                "interim",
                "profile_eligibility_final_application",
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
    inputs = [
        args.inventory,
        args.decision_template,
        args.carry_forward_anchors,
        args.verified_before,
        args.verified_additions,
    ]
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing final application inputs: " + ", ".join(missing))

    output_names = {
        "final_verified": "profile_eligibility_verified_decisions_final.csv",
        "compatible_decisions": "profile_eligibility_decisions_46a_compatible.csv",
        "validated_decisions": "validated_profile_eligibility_decisions.csv",
        "adjudicated_profiles": "adjudicated_cross_source_profiles.csv",
        "included_outcome_profiles": "included_outcome_profiles.csv",
        "candidate_pairs": "physical_location_candidate_pairs.csv",
        "review_blocks": "physical_location_review_blocks.csv",
        "block_triage": "physical_location_block_triage.csv",
        "block_profiles": "physical_location_block_profiles.csv",
    }
    output_paths = {
        key: args.output_directory / name for key, name in output_names.items()
    }
    summary_path = (
        args.output_directory / "profile_eligibility_final_application_summary.json"
    )
    _guard([*output_paths.values(), summary_path], args.overwrite)

    frames, summary = apply_final_verified_freeze(
        _read(args.inventory),
        _read(args.decision_template),
        _read(args.carry_forward_anchors),
        _read(args.verified_before),
        _read(args.verified_additions),
    )
    for key, frame in frames.items():
        _write_csv(frame, output_paths[key])
    summary["input_lineage"] = {
        "inventory": str(args.inventory),
        "decision_template": str(args.decision_template),
        "carry_forward_anchors": str(args.carry_forward_anchors),
        "verified_before": str(args.verified_before),
        "verified_additions": str(args.verified_additions),
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
