"""Parse downloaded Business Info JSON into one profile per requested CID."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from medical_ratings.parsing import parse_business_info_payload


EXPECTED_TASK_COUNT = 769
DEFAULT_RUN_NAME = "rescrape_malone_syracuse_20260907"
DEFAULT_RESULTS_DIRECTORY = (
    Path("data/raw") / DEFAULT_RUN_NAME / "business_info_results"
)
DEFAULT_OUTPUT = (
    Path("data/interim") / DEFAULT_RUN_NAME / "business_info_profiles.csv"
)
REQUIRED_LOG_COLUMNS = {
    "task_id",
    "task_tag",
    "cid",
    "query",
    "download_status",
    "retrieved_at_utc",
    "item_count",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse exact-CID Business Info raw result JSON."
    )
    parser.add_argument(
        "--results-directory",
        type=Path,
        default=DEFAULT_RESULTS_DIRECTORY,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _payload_tag(payload: Mapping[str, Any]) -> str | None:
    tasks = payload.get("tasks") or []
    if len(tasks) != 1 or not isinstance(tasks[0], Mapping):
        return None
    data = tasks[0].get("data")
    if not isinstance(data, Mapping):
        return None
    tag = data.get("tag")
    return None if tag is None else str(tag)


def parse_downloaded_business_info(
    result_log: pd.DataFrame,
    raw_directory: Path,
) -> pd.DataFrame:
    """Validate and parse one downloaded business profile per task."""

    missing = REQUIRED_LOG_COLUMNS - set(result_log.columns)
    if missing:
        raise KeyError(f"Result log is missing columns: {sorted(missing)}")
    latest = result_log.drop_duplicates("task_tag", keep="last").copy()
    downloaded = latest.loc[
        latest["download_status"].isin({"downloaded", "downloaded_empty"})
    ].copy()
    if downloaded.empty:
        raise ValueError("Result log contains no downloaded tasks")
    if not downloaded["task_tag"].is_unique:
        raise ValueError("Downloaded task tags are not unique")

    records: list[dict[str, Any]] = []
    for row in downloaded.to_dict(orient="records"):
        task_id = str(row["task_id"])
        task_tag = str(row["task_tag"])
        expected_cid = str(row["cid"]).strip()
        expected_query = f"cid:{expected_cid}"
        if str(row["query"]) != expected_query:
            raise ValueError(f"Query and CID mismatch in result log for {task_id}")
        raw_path = raw_directory / f"{task_id}.json"
        if not raw_path.is_file():
            raise FileNotFoundError(f"Missing raw result: {raw_path}")
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError(f"Raw result must be a JSON object: {raw_path}")
        raw_tag = _payload_tag(payload)
        if raw_tag != task_tag:
            raise ValueError(
                f"Task tag mismatch for {task_id}: log={task_tag!r}, payload={raw_tag!r}"
            )

        parsed = parse_business_info_payload(
            payload,
            task_id=task_id,
            query=expected_query,
            retrieved_at_utc=str(row["retrieved_at_utc"]),
        )
        expected_items = int(row["item_count"])
        if len(parsed) != expected_items:
            raise ValueError(
                f"Parsed item count mismatch for {task_id}: "
                f"parsed={len(parsed)}, expected={expected_items}"
            )
        if len(parsed) > 1:
            raise ValueError(f"Exact-CID task returned multiple profiles: {task_id}")
        for record in parsed:
            if str(record.get("cid")) != expected_cid:
                raise ValueError(f"Returned CID mismatch for {task_id}")
            if record.get("result_keyword") not in {None, expected_query}:
                raise ValueError(f"Returned keyword mismatch for {task_id}")
        records.extend(parsed)

    profiles = pd.DataFrame.from_records(records)
    if profiles.empty:
        raise ValueError("Downloaded tasks contain no business profiles")
    if profiles["task_id"].duplicated().any():
        raise ValueError("Parsed profiles contain duplicate task IDs")
    if profiles["cid"].astype(str).duplicated().any():
        raise ValueError("Parsed profiles contain duplicate CID values")
    return profiles


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def summarize_profiles(
    profiles: pd.DataFrame,
    *,
    result_task_count: int,
    output_path: Path,
) -> dict[str, Any]:
    return {
        "result_tasks": int(result_task_count),
        "parsed_profiles": len(profiles),
        "unique_cid": int(profiles["cid"].nunique()),
        "unique_place_id": int(profiles["place_id"].nunique()),
        "with_zip": int(profiles["zip"].notna().sum()),
        "with_coordinates": int(
            (profiles["latitude"].notna() & profiles["longitude"].notna()).sum()
        ),
        "with_category": int(profiles["category"].notna().sum()),
        "current_status": {
            str(key): int(value)
            for key, value in profiles["current_status"]
            .fillna("<missing>")
            .value_counts()
            .sort_index()
            .items()
        },
        "output": str(output_path),
    }


def main() -> int:
    args = parse_arguments()
    log_path = args.results_directory / "business_info_result_log.csv"
    raw_directory = args.results_directory / "raw"
    result_log = pd.read_csv(log_path, dtype={"cid": "string"}, low_memory=False)
    latest = result_log.drop_duplicates("task_tag", keep="last")
    if len(latest) != EXPECTED_TASK_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_TASK_COUNT} result tasks, found {len(latest)}"
        )
    profiles = parse_downloaded_business_info(result_log, raw_directory)
    write_csv_atomic(profiles, args.output)
    print(
        json.dumps(
            summarize_profiles(
                profiles,
                result_task_count=len(latest),
                output_path=args.output,
            ),
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
