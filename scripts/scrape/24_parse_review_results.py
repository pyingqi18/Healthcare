"""Parse all audited Google Reviews JSON into a provenance-complete table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.review_result_parsing import (
    parse_audited_review_results,
    summarize_parsed_reviews,
)
from medical_ratings.scrape_safety import expected_task_count
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse all audited Google Reviews raw JSON."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--audit",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--result-log",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--raw-directory",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--zero-review-output",
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
            "audit": ("interim", "review_result_audit.csv"),
            "result_log": ("raw", "review_results/review_result_log.csv"),
            "raw_directory": ("raw", "review_results/raw"),
            "output": ("interim", "reviews_parsed.csv"),
            "zero_review_output": ("interim", "zero_review_locations.csv"),
            "summary": ("interim", "review_parsing_summary.json"),
        },
    )


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def write_json_atomic(content: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(content, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    audit = pd.read_csv(
        args.audit,
        dtype={"cid": "string", "identifier_value": "string"},
        low_memory=False,
    )
    result_log = pd.read_csv(
        args.result_log,
        dtype={"cid": "string", "identifier_value": "string"},
        low_memory=False,
    )
    task_count = expected_task_count(audit)
    reviews, zero_reviews = parse_audited_review_results(
        audit,
        result_log,
        args.raw_directory,
        expected_task_count=task_count,
    )
    summary = summarize_parsed_reviews(
        reviews,
        zero_reviews,
        input_tasks=task_count,
        output_path=args.output,
        zero_review_output=args.zero_review_output,
        summary_output=args.summary,
    )
    if summary["invalid_review_timestamp"]:
        raise ValueError("Parsed reviews contain invalid timestamps")
    if summary["invalid_rating"]:
        raise ValueError("Parsed reviews contain invalid ratings")
    write_csv_atomic(reviews, args.output)
    write_csv_atomic(zero_reviews, args.zero_review_output)
    write_json_atomic(summary, args.summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
