"""Download submitted clinic-search results with resume support."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from medical_ratings.dataforseo import DataForSEOClient


DEFAULT_RUN_DIRECTORY = Path(
    "data/raw/rescrape_malone_syracuse_20260907"
)
REQUIRED_TASK_COLUMNS = {
    "task_tag",
    "task_id",
    "api_type",
    "query",
    "region_key",
    "submission_status",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or download submitted clinic-search results."
    )
    parser.add_argument(
        "--task-log",
        type=Path,
        default=DEFAULT_RUN_DIRECTORY / "clinic_search_task_log.csv",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("config/settings.yaml"),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_RUN_DIRECTORY / "clinic_search_results",
    )
    parser.add_argument(
        "--download-results",
        action="store_true",
        help="Fetch results. Without this flag, only validate the plan.",
    )
    return parser.parse_args()


def build_download_plan(
    task_log: pd.DataFrame,
    raw_directory: Path,
) -> pd.DataFrame:
    """Return one row per submitted task and mark saved raw responses."""

    missing = REQUIRED_TASK_COLUMNS - set(task_log.columns)
    if missing:
        raise KeyError(f"Task log is missing columns: {sorted(missing)}")

    submitted = task_log.loc[
        task_log["submission_status"].eq("submitted")
    ].drop_duplicates("task_tag", keep="last").copy()
    if submitted.empty:
        raise ValueError("Task log contains no submitted tasks")
    if not submitted["task_tag"].is_unique:
        raise ValueError("Submitted task tags are not unique")
    if submitted["task_id"].isna().any():
        raise ValueError("Submitted task log contains missing task IDs")

    submitted["raw_response_path"] = submitted["task_id"].map(
        lambda task_id: str(raw_directory / f"{task_id}.json")
    )
    submitted["already_downloaded"] = submitted[
        "raw_response_path"
    ].map(lambda value: Path(value).is_file())
    return submitted.reset_index(drop=True)


def summarize_task_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize completion without exposing clinic result content."""

    tasks = payload.get("tasks") or []
    if not tasks:
        raise ValueError("Task response contains no tasks")

    task = tasks[0]
    results = task.get("result")
    return {
        "response_status": payload.get("status_code"),
        "task_status": task.get("status_code"),
        "result_ready": results is not None,
        "result_blocks": len(results or []),
        "item_count": sum(
            len(result.get("items") or [])
            for result in (results or [])
        ),
    }


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    """Write one raw response without leaving a partial target file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def append_result_log(path: Path, record: Mapping[str, Any]) -> None:
    """Append one result status using an atomic file replacement."""

    path.parent.mkdir(parents=True, exist_ok=True)
    new_row = pd.DataFrame([record])
    if path.exists():
        existing = pd.read_csv(path, low_memory=False)
        columns = list(dict.fromkeys([*existing.columns, *new_row.columns]))
        updated = pd.concat(
            [existing, new_row],
            ignore_index=True,
        ).reindex(columns=columns)
    else:
        updated = new_row

    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    updated.to_csv(temporary_path, index=False)
    temporary_path.replace(path)


def main() -> int:
    args = parse_arguments()
    task_log = pd.read_csv(args.task_log, low_memory=False)
    raw_directory = args.output_directory / "raw"
    result_log_path = args.output_directory / "clinic_search_result_log.csv"
    plan = build_download_plan(task_log, raw_directory)
    remaining = plan.loc[~plan["already_downloaded"]].copy()

    summary = {
        "submitted_tasks": len(plan),
        "already_downloaded": int(plan["already_downloaded"].sum()),
        "remaining_results": len(remaining),
        "download_enabled": args.download_results,
    }
    print(json.dumps(summary, indent=2))
    if not args.download_results:
        print("Validation only. No result requests were sent.")
        return 0

    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not login or not password:
        raise RuntimeError(
            "Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD first"
        )

    settings = yaml.safe_load(args.settings.read_text(encoding="utf-8"))
    dataforseo = settings["dataforseo"]
    endpoints = dataforseo["endpoints"]
    interval = float(dataforseo.get("request_interval_seconds", 1))
    client = DataForSEOClient(login, password)

    counts = {"downloaded": 0, "not_ready": 0, "failed": 0}
    for row in remaining.to_dict(orient="records"):
        api_type = str(row["api_type"])
        task_id = str(row["task_id"])
        raw_path = Path(str(row["raw_response_path"]))
        retrieved_at = datetime.now(timezone.utc).isoformat()

        try:
            endpoint = str(endpoints[f"{api_type}_get"])
            payload = client.get_task(endpoint, task_id)
            result_summary = summarize_task_payload(payload)
            if not result_summary["result_ready"]:
                status = "not_ready"
            else:
                write_json_atomic(raw_path, payload)
                status = "downloaded"

            append_result_log(
                result_log_path,
                {
                    "task_tag": row["task_tag"],
                    "task_id": task_id,
                    "api_type": api_type,
                    "region_key": row["region_key"],
                    "query": row["query"],
                    "download_status": status,
                    "retrieved_at_utc": retrieved_at,
                    "raw_response_path": str(raw_path),
                    **result_summary,
                    "error_type": None,
                    "error_message": None,
                },
            )
            counts[status] += 1
        except Exception as error:
            append_result_log(
                result_log_path,
                {
                    "task_tag": row["task_tag"],
                    "task_id": task_id,
                    "api_type": api_type,
                    "region_key": row["region_key"],
                    "query": row["query"],
                    "download_status": "failed",
                    "retrieved_at_utc": retrieved_at,
                    "raw_response_path": str(raw_path),
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
            )
            counts["failed"] += 1

        time.sleep(interval)

    print(json.dumps(counts, indent=2))
    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
