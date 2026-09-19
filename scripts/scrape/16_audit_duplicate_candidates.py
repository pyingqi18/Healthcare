"""Audit likely duplicate profiles among final included candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.duplicate_candidate_audit import (
    build_duplicate_candidate_pairs,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build manual-review pairs for possible duplicate profiles."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--candidates",
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
            "output": ("interim", "clinic_duplicate_candidate_pairs.csv"),
            "summary": ("interim", "clinic_duplicate_candidate_summary.json"),
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
    included = candidates.loc[candidates["final_included"].astype(bool)]
    pairs = build_duplicate_candidate_pairs(candidates)
    write_csv_atomic(pairs, args.output)

    flagged_keys = set(pairs["left_clinic_key"]) | set(
        pairs["right_clinic_key"]
    )
    summary = {
        "input_candidates": len(candidates),
        "included_candidates": len(included),
        "review_pairs": len(pairs),
        "candidates_in_review_pairs": len(flagged_keys),
        "pairs_by_priority": {
            str(key): int(value)
            for key, value in pairs["review_priority"]
            .value_counts()
            .sort_index()
            .items()
        },
        "evidence_pair_counts": {
            "same_phone": int(pairs["same_phone"].sum()),
            "same_domain": int(pairs["same_domain"].sum()),
            "same_address": int(pairs["same_address"].sum()),
            "within_50_meters": int(pairs["within_50_meters"].sum()),
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
