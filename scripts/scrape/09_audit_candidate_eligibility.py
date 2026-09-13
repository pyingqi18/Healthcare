"""Create an auditable eligibility review table without final sample selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.candidate_eligibility import (
    apply_candidate_eligibility_review,
)


DEFAULT_RUN_NAME = "rescrape_malone_syracuse_20260907"
DEFAULT_DIRECTORY = Path("data/interim") / DEFAULT_RUN_NAME


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit candidate geography and Google category eligibility."
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=DEFAULT_DIRECTORY / "clinic_candidates.csv",
    )
    parser.add_argument(
        "--category-rules",
        type=Path,
        default=Path("config/google_category_rules.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DIRECTORY / "clinic_candidate_eligibility_review.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=DEFAULT_DIRECTORY / "clinic_candidate_eligibility_summary.json",
    )
    return parser.parse_args()


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary_path, index=False)
    temporary_path.replace(path)


def main() -> int:
    args = parse_arguments()
    candidates = pd.read_csv(args.candidates, low_memory=False)
    category_rules = pd.read_csv(args.category_rules)
    reviewed = apply_candidate_eligibility_review(candidates, category_rules)
    write_csv_atomic(reviewed, args.output)

    summary = {
        "input_candidates": len(candidates),
        "output_review_rows": len(reviewed),
        "unique_clinic_keys": int(reviewed["clinic_key"].nunique()),
        "eligibility_review_status": {
            str(key): int(value)
            for key, value in reviewed["eligibility_review_status"]
            .value_counts()
            .sort_index()
            .items()
        },
        "manual_review_categories": {
            str(key): int(value)
            for key, value in reviewed.loc[
                reviewed["eligibility_review_status"].eq(
                    "manual_category_review"
                ),
                "category",
            ]
            .fillna("<missing>")
            .value_counts()
            .sort_index()
            .items()
        },
        "needs_geography_by_source_status": {
            str(key): int(value)
            for key, value in reviewed.loc[
                reviewed["eligibility_review_status"].eq("needs_geography"),
                "market_assignment_status",
            ]
            .value_counts()
            .sort_index()
            .items()
        },
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
