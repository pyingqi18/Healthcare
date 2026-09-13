"""Download Google Reviews results with resume and identity validation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import time
from typing import Any, Mapping

import pandas as pd
import yaml

from medical_ratings.dataforseo import DataForSEOClient


EXPECTED_TASK_COUNT = 109
DEFAULT_RUN_NAME = "rescrape_malone_syracuse_20260907"
DEFAULT_RAW_DIRECTORY = Path("data/raw") / DEFAULT_RUN_NAME
REQUIRED_TASK_COLUMNS = {
    "task_tag",
    "task_id",
    "final_physical_location_id",
    "clinic_key",
    "cid",
    "identifier_type",
    "identifier_value",
    "requested_location",
    "planned_depth",
    "submission_status",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or download submitted Google Reviews results."
    )
    parser.add_argument(
        "--task-log",
        type=Path,
        default=DEFAULT_RAW_DIRECTORY / "review_task_log.csv",
    )
    parser.add_argument(
        "--settings", type=Path, default=Path("config/settings.yaml")
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_RAW_DIRECTORY / "review_results",
    )
    parser.add_argument(
        "--download-results",
        action="store_true",
        help="Fetch results. Without this flag, only validate the plan.",
    )
    return parser.parse_args()


def read_credentials() -> tuple[str, str]:
    """Read credentials from this process or prompt without saving them."""

    login = os.environ.get("DATAFORSEO_LOGIN")
    if not login:
        login = input("DataForSEO API login: ").strip()
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not password:
        password = getpass.getpass("DataForSEO API password: ").strip()
    if not login or not password:
        raise RuntimeError("DataForSEO login and API password are required")
    return login, password


def build_download_plan(
    task_log: pd.DataFrame,
    raw_directory: Path,
) -> pd.DataFrame:
    """Return one row per successful task and mark saved raw responses."""

    missing = REQUIRED_TASK_COLUMNS - set(task_log.columns)
    if missing:
        raise KeyError(f"Task log is missing columns: {sorted(missing)}")
    submitted = (
        task_log.loc[task_log["submission_status"].eq("submitted")]
        .drop_duplicates("task_tag", keep="last")
        .copy()
    )
    if len(submitted) != EXPECTED_TASK_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_TASK_COUNT} submitted tasks, found {len(submitted)}"
        )
    for column in (
        "task_tag",
        "task_id",
        "final_physical_location_id",
        "clinic_key",
        "cid",
        "identifier_type",
        "identifier_value",
        "requested_location",
    ):
        values = submitted[column].astype("string").str.strip()
        if values.isna().any() or values.eq("").any():
            raise ValueError(f"Submitted task log contains blank {column} values")
    for column in ("task_tag", "task_id", "final_physical_location_id"):
        if submitted[column].duplicated().any():
            raise ValueError(f"Submitted task log contains duplicate {column} values")
    if not set(submitted["identifier_type"]).issubset({"place_id", "cid"}):
        raise ValueError("Submitted task log contains invalid identifier types")
    depth = pd.to_numeric(submitted["planned_depth"], errors="coerce")
    if depth.isna().any() or not depth.between(1, 4490).all():
        raise ValueError("Submitted task log contains invalid review depths")
    submitted["planned_depth"] = depth.astype(int)
    submitted["raw_response_path"] = submitted["task_id"].map(
        lambda task_id: str(raw_directory / f"{task_id}.json")
    )
    submitted["already_downloaded"] = submitted["raw_response_path"].map(
        lambda value: Path(value).is_file()
    )
    return submitted.reset_index(drop=True)


def summarize_review_payload(
    payload: Mapping[str, Any],
    *,
    expected_task_id: str,
    expected_task_tag: str,
    expected_identifier_type: str,
    expected_identifier_value: str,
    planned_depth: int,
) -> dict[str, Any]:
    """Validate task identity and summarize review-result completeness."""

    tasks = payload.get("tasks") or []
    if len(tasks) != 1:
        raise ValueError(f"Expected one response task, found {len(tasks)}")
    task = tasks[0]
    response_task_id = task.get("id")
    if response_task_id is not None and str(response_task_id) != expected_task_id:
        raise ValueError("Response task ID does not match the requested task")
    response_tag = (task.get("data") or {}).get("tag")
    if response_tag is not None and str(response_tag) != expected_task_tag:
        raise ValueError("Response task tag does not match the requested task")

    results = task.get("result")
    if results is None:
        return {
            "response_status": payload.get("status_code"),
            "task_status": task.get("status_code"),
            "result_ready": False,
            "result_blocks": 0,
            "item_count": 0,
            "business_reviews_count": None,
            "depth_exhausted": False,
            "needs_depth_followup": False,
        }

    items: list[Mapping[str, Any]] = []
    observed_identifiers: set[str] = set()
    reviews_counts: list[int] = []
    for result in results:
        value = result.get(expected_identifier_type)
        if value is not None:
            observed_identifiers.add(str(value))
        count = result.get("reviews_count")
        if count is not None:
            reviews_counts.append(int(count))
        items.extend(result.get("items") or [])
    if observed_identifiers and observed_identifiers != {expected_identifier_value}:
        raise ValueError("Review result business identifier does not match task log")
    if results and not observed_identifiers:
        raise ValueError("Review result lacks the requested stable business identifier")

    item_count = len(items)
    business_reviews_count = max(reviews_counts) if reviews_counts else None
    depth_exhausted = item_count >= int(planned_depth)
    needs_followup = (
        business_reviews_count is not None
        and business_reviews_count > item_count
        and depth_exhausted
    )
    return {
        "response_status": payload.get("status_code"),
        "task_status": task.get("status_code"),
        "result_ready": True,
        "result_blocks": len(results),
        "item_count": item_count,
        "business_reviews_count": business_reviews_count,
        "depth_exhausted": depth_exhausted,
        "needs_depth_followup": needs_followup,
    }


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
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
    task_log = pd.read_csv(
        args.task_log,
        dtype={"cid": "string", "place_id": "string"},
        low_memory=False,
    )
    raw_directory = args.output_directory / "raw"
    result_log = args.output_directory / "review_result_log.csv"
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

    login, password = read_credentials()
    settings = yaml.safe_load(args.settings.read_text(encoding="utf-8")) or {}
    dataforseo = settings["dataforseo"]
    endpoint = str(dataforseo["endpoints"]["reviews_get"])
    interval = float(dataforseo.get("review_download_interval_seconds", 0.1))
    client = DataForSEOClient(login, password)
    counts = {
        "downloaded": 0,
        "downloaded_empty": 0,
        "not_ready": 0,
        "needs_depth_followup": 0,
        "failed": 0,
    }

    for row in remaining.to_dict(orient="records"):
        task_id = str(row["task_id"])
        raw_path = Path(str(row["raw_response_path"]))
        retrieved_at = datetime.now(timezone.utc).isoformat()
        try:
            payload = client.get_task(endpoint, task_id)
            result_summary = summarize_review_payload(
                payload,
                expected_task_id=task_id,
                expected_task_tag=str(row["task_tag"]),
                expected_identifier_type=str(row["identifier_type"]),
                expected_identifier_value=str(row["identifier_value"]),
                planned_depth=int(row["planned_depth"]),
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
                    "final_physical_location_id": row[
                        "final_physical_location_id"
                    ],
                    "clinic_key": row["clinic_key"],
                    "cid": row["cid"],
                    "identifier_type": row["identifier_type"],
                    "identifier_value": row["identifier_value"],
                    "requested_location": row["requested_location"],
                    "planned_depth": row["planned_depth"],
                    "download_status": status,
                    "retrieved_at_utc": retrieved_at,
                    "raw_response_path": str(raw_path),
                    **result_summary,
                    "error_type": None,
                    "error_message": None,
                },
            )
            counts[status] += 1
            if result_summary["needs_depth_followup"]:
                counts["needs_depth_followup"] += 1
        except Exception as error:
            append_result_log(
                result_log,
                {
                    "task_tag": row["task_tag"],
                    "task_id": task_id,
                    "final_physical_location_id": row[
                        "final_physical_location_id"
                    ],
                    "clinic_key": row["clinic_key"],
                    "cid": row["cid"],
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
