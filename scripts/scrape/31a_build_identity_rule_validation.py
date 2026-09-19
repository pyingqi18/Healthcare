"""Build a manual validation set for broader historical identity rules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.identity_rule_validation import (
    build_identity_rule_validation,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a manual identity-rule validation queue without API calls."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--review-queue", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "review_queue": (
                "interim",
                "all_market_unmatched_reference_review/"
                "unmatched_reference_review_queue.csv",
            ),
            "output_directory": (
                "interim",
                "identity_rule_validation",
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
        "all": args.output_directory / "identity_rule_validation_all_unmatched.csv",
        "candidates": args.output_directory / "identity_rule_manual_validation_candidates.csv",
        "summary": args.output_directory / "identity_rule_validation_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )
    all_rows, candidates, summary = build_identity_rule_validation(
        pd.read_csv(args.review_queue, low_memory=False)
    )
    write_csv_atomic(all_rows, outputs["all"])
    write_csv_atomic(candidates, outputs["candidates"])
    write_json_atomic(summary, outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
