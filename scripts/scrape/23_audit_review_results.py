"""Audit all downloaded Google Reviews results without API requests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.review_result_audit import (
    audit_downloaded_review_results,
    summarize_review_audit,
)


EXPECTED_TASK_COUNT = 109
DEFAULT_RUN_NAME = "rescrape_malone_syracuse_20260907"
DEFAULT_RAW_DIRECTORY = Path("data/raw") / DEFAULT_RUN_NAME
DEFAULT_INTERIM_DIRECTORY = Path("data/interim") / DEFAULT_RUN_NAME


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit every downloaded Google Reviews raw result."
    )
    parser.add_argument(
        "--task-log",
        type=Path,
        default=DEFAULT_RAW_DIRECTORY / "review_task_log.csv",
    )
    parser.add_argument(
        "--raw-directory",
        type=Path,
        default=DEFAULT_RAW_DIRECTORY / "review_results" / "raw",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_INTERIM_DIRECTORY / "review_result_audit.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=DEFAULT_INTERIM_DIRECTORY / "review_result_audit_summary.json",
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
    task_log = pd.read_csv(
        args.task_log,
        dtype={"cid": "string", "place_id": "string"},
        low_memory=False,
    )
    audit, review_ids = audit_downloaded_review_results(
        task_log,
        args.raw_directory,
        expected_task_count=EXPECTED_TASK_COUNT,
    )
    raw_json_files = sum(1 for _ in args.raw_directory.glob("*.json"))
    if raw_json_files != EXPECTED_TASK_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_TASK_COUNT} raw JSON files, "
            f"found {raw_json_files}"
        )
    summary = summarize_review_audit(
        audit,
        review_ids,
        raw_json_files=raw_json_files,
        audit_output=args.output,
        summary_output=args.summary,
    )
    write_csv_atomic(audit, args.output)
    write_json_atomic(summary, args.summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
