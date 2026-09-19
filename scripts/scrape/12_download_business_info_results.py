"""Download exact-CID Business Info results with resume and identity checks."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from medical_ratings.config import require_dataforseo_credentials
from medical_ratings.dataforseo import DataForSEOClient
from medical_ratings.scrape_safety import submitted_task_rows
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


REQUIRED_TASK_COLUMNS = {
    "task_tag",
    "task_id",
    "cid",
    "query",
    "submission_status",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or download exact-CID Business Info results."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--task-log",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("config/settings.yaml"),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--download-results",
        action="store_true",
        help="Fetch results. Without this flag, only validate the plan.",
    )
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "task_log": ("raw", "business_info_task_log.csv"),
            "output_directory": ("raw", "business_info_results"),
        },
    )


def build_download_plan(
    task_log: pd.DataFrame,
    raw_directory: Path,
) -> pd.DataFrame:
    """Return one row per successful task and mark saved raw responses."""

    missing = REQUIRED_TASK_COLUMNS - set(task_log.columns)
    if missing:
        raise KeyError(f"Task log is missing columns: {sorted(missing)}")
    submitted = submitted_task_rows(
        task_log,
        required_columns=REQUIRED_TASK_COLUMNS,
    )
    if submitted["task_id"].isna().any():
        raise ValueError("Submitted task log contains missing task IDs")
    if not submitted["task_tag"].is_unique:
        raise ValueError("Submitted task tags are not unique")

    cid = submitted["cid"].astype("string").str.strip()
    if (~cid.str.fullmatch(r"\d+")).any():
        raise ValueError("Submitted task log contains invalid cid values")
    if not (submitted["query"].astype("string") == "cid:" + cid).all():
        raise ValueError("Submitted task queries do not match their cid values")
    submitted["cid"] = cid
    submitted["raw_response_path"] = submitted["task_id"].map(
        lambda task_id: str(raw_directory / f"{task_id}.json")
    )
    submitted["already_downloaded"] = submitted["raw_response_path"].map(
        lambda value: Path(value).is_file()
    )
    return submitted.reset_index(drop=True)


def summarize_task_payload(
    payload: Mapping[str, Any],
    *,
    expected_task_id: str,
    expected_cid: str,
) -> dict[str, Any]:
    """Validate task and CID identity, then summarize completion."""

    tasks = payload.get("tasks") or []
    if len(tasks) != 1:
        raise ValueError(f"Expected one response task, found {len(tasks)}")
    task = tasks[0]
    response_task_id = task.get("id")
    if response_task_id is not None and str(response_task_id) != expected_task_id:
        raise ValueError("Response task ID does not match the requested task")

    results = task.get("result")
    if results is None:
        return {
            "response_status": payload.get("status_code"),
            "task_status": task.get("status_code"),
            "result_ready": False,
            "result_blocks": 0,
            "item_count": 0,
        }

    expected_query = f"cid:{expected_cid}"
    items: list[Mapping[str, Any]] = []
    for result in results:
        keyword = result.get("keyword")
        if keyword is not None and str(keyword) != expected_query:
            raise ValueError("Business Info result keyword does not match expected CID")
        items.extend(result.get("items") or [])

    observed_item_cids = {
        str(item.get("cid"))
        for item in items
        if item.get("cid") is not None
    }
    if observed_item_cids and observed_item_cids != {expected_cid}:
        raise ValueError(
            "Business Info result contains a CID different from the requested CID"
        )
    return {
        "response_status": payload.get("status_code"),
        "task_status": task.get("status_code"),
        "result_ready": True,
        "result_blocks": len(results),
        "item_count": len(items),
    }


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def append_result_log(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    addition = pd.DataFrame([record])
    if path.exists():
        existing = pd.read_csv(path, low_memory=False)
        columns = list(dict.fromkeys([*existing.columns, *addition.columns]))
        updated = pd.concat([existing, addition], ignore_index=True).reindex(
            columns=columns
        )
    else:
        updated = addition
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    updated.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    task_log = pd.read_csv(args.task_log, dtype={"cid": "string"}, low_memory=False)
    raw_directory = args.output_directory / "raw"
    result_log = args.output_directory / "business_info_result_log.csv"
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

    login, password = require_dataforseo_credentials()
    settings = yaml.safe_load(args.settings.read_text(encoding="utf-8"))
    dataforseo = settings["dataforseo"]
    endpoint = str(dataforseo["endpoints"]["business_info_get"])
    interval = float(
        dataforseo.get("business_info_download_interval_seconds", 0.1)
    )
    client = DataForSEOClient(login, password)
    counts = {"downloaded": 0, "downloaded_empty": 0, "not_ready": 0, "failed": 0}

    for row in remaining.to_dict(orient="records"):
        task_id = str(row["task_id"])
        cid = str(row["cid"])
        raw_path = Path(str(row["raw_response_path"]))
        retrieved_at = datetime.now(timezone.utc).isoformat()
        try:
            payload = client.get_task(endpoint, task_id)
            result_summary = summarize_task_payload(
                payload,
                expected_task_id=task_id,
                expected_cid=cid,
            )
            if not result_summary["result_ready"]:
                status = "not_ready"
            else:
                write_json_atomic(raw_path, payload)
                status = (
                    "downloaded"
                    if result_summary["item_count"] > 0
                    else "downloaded_empty"
                )
            append_result_log(
                result_log,
                {
                    "task_tag": row["task_tag"],
                    "task_id": task_id,
                    "clinic_key": row.get("clinic_key"),
                    "cid": cid,
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
                result_log,
                {
                    "task_tag": row["task_tag"],
                    "task_id": task_id,
                    "clinic_key": row.get("clinic_key"),
                    "cid": cid,
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
