"""Build physical-location groups and canonical-profile suggestions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.physical_location_groups import (
    build_physical_location_review,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Group included Google profiles by physical dental location."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--candidates",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--pairs",
        type=Path,
        default=None,
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
            "candidates": ("interim", "clinic_candidates_final_review.csv"),
            "pairs": ("interim", "clinic_duplicate_candidate_pairs.csv"),
            "output": ("interim", "physical_location_group_review.csv"),
            "summary": ("interim", "physical_location_group_summary.json"),
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
    pairs = pd.read_csv(
        args.pairs,
        dtype={"left_cid": "string", "right_cid": "string"},
        low_memory=False,
    )
    review = build_physical_location_review(candidates, pairs)
    write_csv_atomic(review, args.output)

    grouped = review.loc[review["location_group_size"].gt(1)]
    summary = {
        "included_google_profiles": len(review),
        "suggested_physical_locations": int(
            review["physical_location_group"].nunique()
        ),
        "singleton_locations": int(
            review.loc[review["location_group_size"].eq(1),
                       "physical_location_group"].nunique()
        ),
        "location_groups_requiring_review": int(
            grouped["physical_location_group"].nunique()
        ),
        "profiles_in_location_groups": len(grouped),
        "suggested_profiles_to_absorb": int(
            (~review["suggested_canonical_profile"]).sum()
        ),
        "groups_by_market": {
            str(key): int(value)
            for key, value in review.drop_duplicates("physical_location_group")
            ["mapped_location"].value_counts().sort_index().items()
        },
        "profile_roles": {
            str(key): int(value)
            for key, value in review["profile_role"]
            .value_counts()
            .sort_index()
            .items()
        },
        "automatic_merges": 0,
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
