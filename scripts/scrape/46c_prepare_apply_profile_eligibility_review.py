"""Prepare or apply the consolidated profile-eligibility review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.profile_eligibility_review import (
    apply_profile_eligibility_review,
    prepare_profile_eligibility_review,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare row-plus-review-block eligibility files, or expand completed "
            "human decisions into the exact decision file required by stage 46a."
        )
    )
    add_run_context_arguments(parser)
    parser.add_argument("--triage", type=Path, default=None)
    parser.add_argument("--groups", type=Path, default=None)
    parser.add_argument("--inventory", type=Path, default=None)
    parser.add_argument(
        "--verified-decisions",
        type=Path,
        default=Path("config/profile_eligibility_verified_decisions_20260924.csv"),
    )
    parser.add_argument("--blank-decisions", type=Path, default=None)
    parser.add_argument("--row-decisions", type=Path, default=None)
    parser.add_argument("--group-decisions", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--apply-reviewed", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "triage": ("interim", "profile_eligibility_triage/profile_eligibility_triage.csv"),
            "groups": (
                "interim",
                "profile_eligibility_triage/profile_eligibility_category_groups.csv",
            ),
            "blank_decisions": (
                "interim",
                "cross_source_profile_location_review/profile_eligibility_decisions.csv",
            ),
            "inventory": (
                "interim",
                "cross_source_profile_location_review/unified_cross_source_profile_inventory.csv",
            ),
            "output_directory": ("interim", "profile_eligibility_review"),
        },
    )


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _check_outputs(paths: list[Path], overwrite: bool) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(existing) + ". Use --overwrite."
        )


def main() -> int:
    args = parse_arguments()
    if args.apply_reviewed:
        if args.row_decisions is None or args.group_decisions is None:
            raise ValueError(
                "--apply-reviewed requires --row-decisions and --group-decisions"
            )
        inputs = [args.blank_decisions, args.row_decisions, args.group_decisions]
        outputs = [
            args.output_directory / "profile_eligibility_decisions_completed.csv",
            args.output_directory / "profile_eligibility_decision_audit.csv",
            args.output_directory / "profile_eligibility_review_apply_summary.json",
        ]
        missing = [str(path) for path in inputs if not path.exists()]
        if missing:
            raise FileNotFoundError("Missing review inputs: " + ", ".join(missing))
        _check_outputs(outputs, args.overwrite)
        completed, audit, summary = apply_profile_eligibility_review(
            pd.read_csv(args.blank_decisions, dtype=str, keep_default_na=False),
            pd.read_csv(args.row_decisions, dtype=str, keep_default_na=False),
            pd.read_csv(args.group_decisions, dtype=str, keep_default_na=False),
        )
        _write_csv(completed, outputs[0])
        _write_csv(audit, outputs[1])
        _write_json(summary, outputs[2])
    else:
        inputs = [
            args.triage,
            args.groups,
            args.inventory,
            args.verified_decisions,
        ]
        outputs = [
            args.output_directory / "profile_eligibility_review_rows.csv",
            args.output_directory / "profile_eligibility_review_groups.csv",
            args.output_directory / "profile_eligibility_review_prepare_summary.json",
        ]
        missing = [str(path) for path in inputs if not path.exists()]
        if missing:
            raise FileNotFoundError("Missing review inputs: " + ", ".join(missing))
        _check_outputs(outputs, args.overwrite)
        rows, groups, summary = prepare_profile_eligibility_review(
            pd.read_csv(args.triage, dtype=str, keep_default_na=False, low_memory=False),
            pd.read_csv(args.groups, dtype=str, keep_default_na=False, low_memory=False),
            pd.read_csv(args.inventory, dtype=str, keep_default_na=False, low_memory=False),
            pd.read_csv(
                args.verified_decisions,
                dtype=str,
                keep_default_na=False,
                low_memory=False,
            ),
        )
        _write_csv(rows, outputs[0])
        _write_csv(groups, outputs[1])
        _write_json(summary, outputs[2])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
