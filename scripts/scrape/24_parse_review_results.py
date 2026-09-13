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


EXPECTED_TASK_COUNT = 109
DEFAULT_RUN_NAME = "rescrape_malone_syracuse_20260907"
DEFAULT_RAW_DIRECTORY = Path("data/raw") / DEFAULT_RUN_NAME
DEFAULT_INTERIM_DIRECTORY = Path("data/interim") / DEFAULT_RUN_NAME


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse all audited Google Reviews raw JSON."
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=DEFAULT_INTERIM_DIRECTORY / "review_result_audit.csv",
    )
    parser.add_argument(
        "--result-log",
        type=Path,
        default=DEFAULT_RAW_DIRECTORY
        / "review_results"
        / "review_result_log.csv",
    )
    parser.add_argument(
        "--raw-directory",
        type=Path,
        default=DEFAULT_RAW_DIRECTORY / "review_results" / "raw",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_INTERIM_DIRECTORY / "reviews_parsed.csv",
    )
    parser.add_argument(
        "--zero-review-output",
        type=Path,
        default=DEFAULT_INTERIM_DIRECTORY / "zero_review_locations.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=DEFAULT_INTERIM_DIRECTORY / "review_parsing_summary.json",
    )
    return parser.parse_args()


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
    reviews, zero_reviews = parse_audited_review_results(
        audit,
        result_log,
        args.raw_directory,
        expected_task_count=EXPECTED_TASK_COUNT,
    )
    summary = summarize_parsed_reviews(
        reviews,
        zero_reviews,
        input_tasks=EXPECTED_TASK_COUNT,
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
