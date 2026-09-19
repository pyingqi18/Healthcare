"""Parse downloaded clinic-search JSON into one provenance-complete table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from medical_ratings.parsing import (
    parse_local_finder_payload,
    parse_maps_payload,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


REQUIRED_LOG_COLUMNS = {
    "task_id",
    "task_tag",
    "api_type",
    "query",
    "region_key",
    "download_status",
    "retrieved_at_utc",
}
PARSERS = {
    "maps": parse_maps_payload,
    "local_finder": parse_local_finder_payload,
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse downloaded Maps and Local Finder result JSON."
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
    )
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "results_directory": ("raw", "clinic_search_results"),
            "output": ("interim", "clinic_search_observations.csv"),
        },
    )


def _payload_tag(payload: Mapping[str, Any]) -> str | None:
    tasks = payload.get("tasks") or []
    if not tasks or not isinstance(tasks[0], Mapping):
        return None
    data = tasks[0].get("data")
    if not isinstance(data, Mapping):
        return None
    tag = data.get("tag")
    return None if tag is None else str(tag)


def parse_downloaded_results(
    result_log: pd.DataFrame,
    raw_directory: Path,
) -> pd.DataFrame:
    """Parse every downloaded task while preserving all search observations."""

    missing = REQUIRED_LOG_COLUMNS - set(result_log.columns)
    if missing:
        raise KeyError(f"Result log is missing columns: {sorted(missing)}")

    downloaded = (
        result_log.loc[result_log["download_status"].eq("downloaded")]
        .drop_duplicates("task_tag", keep="last")
        .copy()
    )
    if downloaded.empty:
        raise ValueError("Result log contains no downloaded tasks")
    if not downloaded["task_tag"].is_unique:
        raise ValueError("Downloaded task tags are not unique")

    records: list[dict[str, Any]] = []
    expected_item_count = 0
    for row in downloaded.to_dict(orient="records"):
        api_type = str(row["api_type"])
        parser = PARSERS.get(api_type)
        if parser is None:
            raise ValueError(f"Unsupported api_type: {api_type}")

        task_id = str(row["task_id"])
        task_tag = str(row["task_tag"])
        raw_path = raw_directory / f"{task_id}.json"
        if not raw_path.is_file():
            raise FileNotFoundError(f"Missing raw result: {raw_path}")
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError(f"Raw result must be a JSON object: {raw_path}")

        raw_tag = _payload_tag(payload)
        if raw_tag != task_tag:
            raise ValueError(
                f"Task tag mismatch for {task_id}: "
                f"log={task_tag!r}, payload={raw_tag!r}"
            )

        parsed = parser(
            payload,
            task_id=task_id,
            query=str(row["query"]),
            requested_location=str(row["region_key"]),
            retrieved_at_utc=str(row["retrieved_at_utc"]),
        )
        records.extend(parsed)
        if "item_count" in row and pd.notna(row["item_count"]):
            expected_item_count += int(row["item_count"])
        else:
            expected_item_count += len(parsed)

    observations = pd.DataFrame.from_records(records)
    if len(observations) != expected_item_count:
        raise ValueError(
            "Parsed observation count does not match the result log: "
            f"parsed={len(observations)}, expected={expected_item_count}"
        )
    if observations.empty:
        raise ValueError("Downloaded tasks contain no search observations")
    if observations["cid"].isna().any():
        raise ValueError("Parsed observations contain missing cid values")
    return observations


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary_path, index=False)
    temporary_path.replace(path)


def summarize_observations(
    observations: pd.DataFrame,
    *,
    output_path: Path,
) -> dict[str, Any]:
    return {
        "parsed_observations": len(observations),
        "observations_by_api": {
            str(key): int(value)
            for key, value in observations["source_api"].value_counts().sort_index().items()
        },
        "observations_by_region": {
            str(key): int(value)
            for key, value in observations["requested_location"]
            .value_counts()
            .sort_index()
            .items()
        },
        "unique_cid": int(observations["cid"].nunique()),
        "unique_place_id": int(observations["place_id"].nunique()),
        "missing_cid": int(observations["cid"].isna().sum()),
        "output": str(output_path),
    }


def main() -> int:
    args = parse_arguments()
    log_path = args.results_directory / "clinic_search_result_log.csv"
    raw_directory = args.results_directory / "raw"
    result_log = pd.read_csv(log_path, low_memory=False)
    observations = parse_downloaded_results(result_log, raw_directory)
    write_csv_atomic(observations, args.output)
    print(
        json.dumps(
            summarize_observations(observations, output_path=args.output),
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
