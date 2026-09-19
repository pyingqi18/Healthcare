"""Apply the frozen manual review of broader historical identity candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.identity_rule_adjudication import (
    apply_identity_rule_adjudication,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply reviewed identity decisions without API requests."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument(
        "--decisions",
        type=Path,
        default=Path("config/identity_rule_manual_decisions_20260919.csv"),
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "candidates": (
                "interim",
                "identity_rule_validation/identity_rule_manual_validation_candidates.csv",
            ),
            "output_directory": (
                "interim",
                "identity_rule_adjudication",
            ),
        },
    )


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def write_json_atomic(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    outputs = {
        "reviewed": args.output_directory / "identity_rule_reviewed_candidates.csv",
        "confirmed": args.output_directory / "identity_rule_confirmed_matches.csv",
        "exclusions": args.output_directory / "identity_rule_reference_exclusions.csv",
        "summary": args.output_directory / "identity_rule_adjudication_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )
    reviewed, confirmed, exclusions, summary = apply_identity_rule_adjudication(
        pd.read_csv(args.candidates, low_memory=False),
        pd.read_csv(args.decisions, low_memory=False),
    )
    write_csv_atomic(reviewed, outputs["reviewed"])
    write_csv_atomic(confirmed, outputs["confirmed"])
    write_csv_atomic(exclusions, outputs["exclusions"])
    write_json_atomic(summary, outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
