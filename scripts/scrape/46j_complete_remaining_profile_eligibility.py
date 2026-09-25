"""Prepare or apply the single remaining-profile eligibility audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.profile_eligibility_completion import (
    apply_remaining_completion,
    prepare_remaining_completion,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_context_arguments(parser)
    parser.add_argument("--remaining", type=Path, default=None)
    parser.add_argument("--verified-decisions", type=Path, default=None)
    parser.add_argument("--decisions", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "remaining": (
                "interim",
                "profile_eligibility_priority_audit/remaining_singleton_profile_audit.csv",
            ),
            "verified_decisions": (
                "interim",
                "profile_eligibility_priority_audit/"
                "profile_eligibility_verified_decisions_updated.csv",
            ),
            "output_directory": ("interim", "profile_eligibility_completion"),
        },
    )


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


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


def _guard(paths: list[Path], overwrite: bool) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(existing) + ". Use --overwrite."
        )


def main() -> int:
    args = parse_arguments()
    inputs = [args.remaining, args.verified_decisions]
    if args.decisions is not None:
        inputs.append(args.decisions)
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing completion inputs: " + ", ".join(missing))

    remaining = _read(args.remaining)
    verified = _read(args.verified_decisions)
    prepared, groups, preparation = prepare_remaining_completion(remaining, verified)
    if args.decisions is None:
        outputs = [
            args.output_directory / "remaining_profile_decisions.csv",
            args.output_directory / "remaining_profile_organization_index.csv",
            args.output_directory / "profile_eligibility_completion_prepare_summary.json",
        ]
        _guard(outputs, args.overwrite)
        _write_csv(prepared, outputs[0])
        _write_csv(groups, outputs[1])
        preparation["input_lineage"] = {
            "remaining_profiles": str(args.remaining),
            "verified_decisions_before": str(args.verified_decisions),
        }
        _write_json(preparation, outputs[2])
        print(json.dumps(preparation, ensure_ascii=False, indent=2))
        return 0

    outputs = [
        args.output_directory / "remaining_profile_verified_additions.csv",
        args.output_directory / "profile_eligibility_verified_decisions_final.csv",
        args.output_directory / "profile_eligibility_completion_apply_summary.json",
    ]
    _guard(outputs, args.overwrite)
    additions, combined, summary = apply_remaining_completion(
        remaining, prepared, _read(args.decisions), verified
    )
    _write_csv(additions, outputs[0])
    _write_csv(combined, outputs[1])
    summary["input_lineage"] = {
        "remaining_profiles": str(args.remaining),
        "verified_decisions_before": str(args.verified_decisions),
        "reviewed_remaining_decisions": str(args.decisions),
    }
    _write_json(summary, outputs[2])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
