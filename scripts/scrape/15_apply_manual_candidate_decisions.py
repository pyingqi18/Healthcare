"""Apply the reviewed decision manifest and freeze the final candidate table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.manual_candidate_review import (
    UNRESOLVED_STATUSES,
    apply_manual_candidate_decisions,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply exact manual decisions to unresolved candidates."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--candidates",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--decisions",
        type=Path,
        required=True,
        help="Run-specific reviewed candidate decision file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "candidates": ("interim", "clinic_candidates_enriched_review.csv"),
            "output": ("interim", "clinic_candidates_final_review.csv"),
            "summary": ("interim", "clinic_candidates_final_summary.json"),
        },
    )


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    candidates = pd.read_csv(
        args.candidates,
        dtype={"cid": "string", "zip": "string"},
        low_memory=False,
    )
    decisions = pd.read_csv(args.decisions, dtype={"cid": "string"})
    reviewed = apply_manual_candidate_decisions(candidates, decisions)
    write_csv_atomic(reviewed, args.output)

    unresolved = reviewed["eligibility_review_status"].isin(
        UNRESOLVED_STATUSES
    )
    included = reviewed.loc[reviewed["final_included"]]
    summary = {
        "input_candidates": len(candidates),
        "manual_decisions_applied": int(reviewed["manual_review_applied"].sum()),
        "manual_decisions_by_status": {
            str(key): int(value)
            for key, value in decisions["manual_decision"]
            .value_counts()
            .sort_index()
            .items()
        },
        "output_candidates": len(reviewed),
        "unique_clinic_keys": int(reviewed["clinic_key"].nunique()),
        "final_eligibility_status": {
            str(key): int(value)
            for key, value in reviewed["eligibility_review_status"]
            .value_counts()
            .sort_index()
            .items()
        },
        "included_by_market": {
            str(key): int(value)
            for key, value in included["mapped_location"]
            .value_counts()
            .sort_index()
            .items()
        },
        "unresolved_candidates": int(unresolved.sum()),
        "output": str(args.output),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    temporary_summary = args.summary.with_suffix(f"{args.summary.suffix}.tmp")
    temporary_summary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_summary.replace(args.summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
