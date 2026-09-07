"""Submit a clinic-search manifest with explicit paid-task confirmation."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.dataforseo import DataForSEOClient


CONFIRMATION_TEXT = "SUBMIT_212_PAID_TASKS"
REQUIRED_MANIFEST_COLUMNS = {
    "task_tag",
    "region_key",
    "location_code",
    "api_type",
    "query",
    "language_code",
    "depth",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or submit a corrected-location search manifest."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("config/settings.yaml"),
    )
    parser.add_argument("--task-log", type=Path, required=True)
    parser.add_argument(
        "--confirm-submit",
        default=None,
        help=(
            "Paid submission is enabled only when this equals "
            f"{CONFIRMATION_TEXT}."
        ),
    )
    return parser.parse_args()


def read_settings(path: Path) -> dict[str, object]:
    settings = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return settings


def validate_manifest(manifest: pd.DataFrame) -> None:
    missing = REQUIRED_MANIFEST_COLUMNS - set(manifest.columns)
    if missing:
        raise KeyError(f"Manifest is missing columns: {sorted(missing)}")
    if manifest.empty:
        raise ValueError("Manifest contains no tasks")
    if manifest["task_tag"].isna().any():
        raise ValueError("Manifest contains missing task_tag values")
    if not manifest["task_tag"].is_unique:
        raise ValueError("Manifest contains duplicate task_tag values")

    valid_api_types = {"maps", "local_finder"}
    unknown_api_types = set(manifest["api_type"]) - valid_api_types
    if unknown_api_types:
        raise ValueError(
            f"Manifest contains unknown api_type values: "
            f"{sorted(unknown_api_types)}"
        )

    invalid_codes = {1026588, 1027001}
    observed_codes = set(manifest["location_code"].astype(int))
    if observed_codes & invalid_codes:
        raise ValueError(
            "Manifest contains a known invalid location code"
        )


def load_submitted_tags(path: Path) -> set[str]:
    if not path.exists():
        return set()

    task_log = pd.read_csv(path, low_memory=False)
    required = {"task_tag", "submission_status"}
    missing = required - set(task_log.columns)
    if missing:
        raise KeyError(f"Task log is missing columns: {sorted(missing)}")

    return set(
        task_log.loc[
            task_log["submission_status"].eq("submitted"),
            "task_tag",
        ].astype(str)
    )


def append_task_log(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record_frame = pd.DataFrame([record])

    if path.exists():
        existing = pd.read_csv(path, low_memory=False)
        columns = list(
            dict.fromkeys(
                [*existing.columns, *record_frame.columns]
            )
        )
        updated = pd.concat(
            [existing, record_frame],
            ignore_index=True,
        ).reindex(columns=columns)
    else:
        updated = record_frame

    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    updated.to_csv(temporary_path, index=False)
    temporary_path.replace(path)


def main() -> None:
    args = parse_arguments()
    manifest = pd.read_csv(args.manifest, low_memory=False)
    validate_manifest(manifest)

    submitted_tags = load_submitted_tags(args.task_log)
    remaining = manifest[
        ~manifest["task_tag"].astype(str).isin(submitted_tags)
    ].copy()

    validation_summary = {
        "manifest_rows": len(manifest),
        "unique_task_tags": int(manifest["task_tag"].nunique()),
        "previously_submitted_tasks": len(submitted_tags),
        "remaining_tasks": len(remaining),
        "location_codes": sorted(
            int(value) for value in manifest["location_code"].unique()
        ),
        "paid_submission_enabled": (
            args.confirm_submit == CONFIRMATION_TEXT
        ),
    }
    print(json.dumps(validation_summary, indent=2))

    if args.confirm_submit != CONFIRMATION_TEXT:
        print(
            "Validation only. No API requests were submitted."
        )
        return

    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not login or not password:
        raise RuntimeError(
            "Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD before submission"
        )

    settings = read_settings(args.settings)
    dataforseo = settings.get("dataforseo")
    if not isinstance(dataforseo, dict):
        raise KeyError("settings.yaml is missing dataforseo")
    endpoints = dataforseo.get("endpoints")
    if not isinstance(endpoints, dict):
        raise KeyError("settings.yaml is missing dataforseo.endpoints")

    endpoint_by_api = {
        "maps": str(endpoints["maps_post"]),
        "local_finder": str(endpoints["local_finder_post"]),
    }
    interval = float(
        dataforseo.get("request_interval_seconds", 1)
    )
    client = DataForSEOClient(login, password)

    for row in remaining.to_dict(orient="records"):
        task_tag = str(row["task_tag"])
        api_type = str(row["api_type"])

        try:
            task_record = client.submit_task(
                url=endpoint_by_api[api_type],
                api_type=api_type,
                query=str(row["query"]),
                location_code=int(row["location_code"]),
                language_code=str(row["language_code"]),
                depth=int(row["depth"]),
                tag=task_tag,
            )
        except Exception as error:
            append_task_log(
                args.task_log,
                {
                    **row,
                    "submission_status": "failed",
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
            )
            raise

        append_task_log(
            args.task_log,
            {
                **row,
                **task_record.to_dict(),
                "submission_status": "submitted",
                "error_type": None,
                "error_message": None,
            },
        )
        time.sleep(interval)


if __name__ == "__main__":
    main()
