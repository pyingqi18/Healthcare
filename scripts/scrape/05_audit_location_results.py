"""Audit downloaded clinic-search JSON before parsing and deduplication."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.result_audit import audit_location_results
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


REQUIRED_LOG_COLUMNS = {
    "task_id",
    "task_tag",
    "api_type",
    "region_key",
    "download_status",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit downloaded result structure without showing clinics."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--results-directory",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Defaults to RESULTS_DIRECTORY/location_result_audit.json.",
    )
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {"results_directory": ("raw", "clinic_search_results")},
    )


def load_downloaded_results(results_directory: Path) -> list[dict[str, Any]]:
    log_path = results_directory / "clinic_search_result_log.csv"
    raw_directory = results_directory / "raw"
    log = pd.read_csv(log_path, low_memory=False)
    missing = REQUIRED_LOG_COLUMNS - set(log.columns)
    if missing:
        raise KeyError(f"Result log is missing columns: {sorted(missing)}")

    downloaded = (
        log.loc[log["download_status"].eq("downloaded")]
        .drop_duplicates("task_tag", keep="last")
        .copy()
    )
    if downloaded.empty:
        raise ValueError("Result log contains no downloaded tasks")
    if not downloaded["task_tag"].is_unique:
        raise ValueError("Downloaded task tags are not unique")

    entries: list[dict[str, Any]] = []
    missing_files: list[str] = []
    for row in downloaded.to_dict(orient="records"):
        task_id = str(row["task_id"])
        raw_path = raw_directory / f"{task_id}.json"
        if not raw_path.is_file():
            missing_files.append(raw_path.name)
            continue
        entries.append(
            {
                "task_id": task_id,
                "task_tag": row["task_tag"],
                "api_type": row["api_type"],
                "region_key": row["region_key"],
                "payload": json.loads(raw_path.read_text(encoding="utf-8")),
            }
        )

    if missing_files:
        sample = ", ".join(missing_files[:5])
        raise FileNotFoundError(
            f"Missing {len(missing_files)} raw JSON files. First files: {sample}"
        )
    return entries


def main() -> int:
    args = parse_arguments()
    output_path = args.output or (
        args.results_directory / "location_result_audit.json"
    )
    entries = load_downloaded_results(args.results_directory)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **audit_location_results(entries),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_path.replace(output_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Saved aggregate audit: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
