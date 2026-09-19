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
from medical_ratings.scrape_safety import expected_task_count
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit every downloaded Google Reviews raw result."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--task-log",
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
        "--summary",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "task_log": ("raw", "review_task_log.csv"),
            "raw_directory": ("raw", "review_results/raw"),
            "output": ("interim", "review_result_audit.csv"),
            "summary": ("interim", "review_result_audit_summary.json"),
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
    task_log = pd.read_csv(
        args.task_log,
        dtype={"cid": "string", "place_id": "string"},
        low_memory=False,
    )
    submitted = task_log.loc[
        task_log["submission_status"].eq("submitted")
    ].drop_duplicates("task_tag", keep="last")
    task_count = expected_task_count(submitted)
    audit, review_ids = audit_downloaded_review_results(
        task_log,
        args.raw_directory,
        expected_task_count=task_count,
    )
    raw_json_files = sum(1 for _ in args.raw_directory.glob("*.json"))
    if raw_json_files != task_count:
        raise ValueError(
            f"Expected {task_count} raw JSON files, "
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
