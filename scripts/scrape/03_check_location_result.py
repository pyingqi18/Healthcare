"""Inspect one submitted clinic-search task without printing raw results."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from medical_ratings.dataforseo import DataForSEOClient


DEFAULT_TASK_LOG = Path(
    "data/raw/rescrape_malone_syracuse_20260907/"
    "clinic_search_task_log.csv"
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether one submitted search task has results."
    )
    parser.add_argument("--task-log", type=Path, default=DEFAULT_TASK_LOG)
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("config/settings.yaml"),
    )
    parser.add_argument(
        "--task-tag",
        default=None,
        help="Inspect this task tag. Defaults to the first submitted task.",
    )
    return parser.parse_args()


def select_submitted_task(
    task_log: pd.DataFrame,
    task_tag: str | None = None,
) -> Mapping[str, Any]:
    """Select one unique successfully submitted task."""

    required = {"task_tag", "task_id", "api_type", "submission_status"}
    missing = required - set(task_log.columns)
    if missing:
        raise KeyError(f"Task log is missing columns: {sorted(missing)}")

    submitted = task_log.loc[
        task_log["submission_status"].eq("submitted")
    ].drop_duplicates("task_tag", keep="last")

    if task_tag is not None:
        submitted = submitted.loc[
            submitted["task_tag"].astype(str).eq(task_tag)
        ]
    if submitted.empty:
        raise ValueError("No matching submitted task was found")

    return submitted.iloc[0].to_dict()


def summarize_task_payload(
    payload: Mapping[str, Any],
    *,
    api_type: str,
) -> dict[str, Any]:
    """Return completion and item counts without exposing result content."""

    tasks = payload.get("tasks") or []
    if not tasks:
        raise ValueError("Task response contains no tasks")

    task = tasks[0]
    results = task.get("result")
    item_count = sum(
        len(result.get("items") or [])
        for result in (results or [])
    )
    return {
        "api_type": api_type,
        "response_status": payload.get("status_code"),
        "task_status": task.get("status_code"),
        "result_ready": results is not None,
        "result_blocks": len(results or []),
        "item_count": item_count,
    }


def main() -> int:
    args = parse_arguments()
    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not login or not password:
        raise RuntimeError(
            "Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD first"
        )

    task_log = pd.read_csv(args.task_log, low_memory=False)
    row = select_submitted_task(task_log, args.task_tag)

    settings = yaml.safe_load(args.settings.read_text(encoding="utf-8"))
    endpoints = settings["dataforseo"]["endpoints"]
    api_type = str(row["api_type"])
    endpoint = str(endpoints[f"{api_type}_get"])

    client = DataForSEOClient(login, password)
    payload = client.get_task(endpoint, str(row["task_id"]))
    summary = summarize_task_payload(payload, api_type=api_type)

    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
