"""Validate or submit exact-CID Business Info tasks in resumable batches."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.config import require_dataforseo_credentials
from medical_ratings.dataforseo import DataForSEOClient
from medical_ratings.scrape_safety import paid_confirmation_text
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


MAXIMUM_BATCH_SIZE = 100
REQUIRED_MANIFEST_COLUMNS = {
    "task_tag",
    "clinic_key",
    "cid",
    "query",
    "location_code",
    "language_code",
    "priority",
    "estimated_unit_cost_usd",
}
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or submit paid Business Info backfill tasks."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("config/settings.yaml"),
    )
    parser.add_argument(
        "--task-log",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--confirm-submit",
        default=None,
        help="Exact confirmation text printed by validation mode.",
    )
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "manifest": ("interim", "business_info_backfill_manifest.csv"),
            "task_log": ("raw", "business_info_task_log.csv"),
        },
    )


def validate_manifest(manifest: pd.DataFrame) -> None:
    missing = REQUIRED_MANIFEST_COLUMNS - set(manifest.columns)
    if missing:
        raise KeyError(f"Manifest is missing columns: {sorted(missing)}")
    if manifest.empty:
        raise ValueError("Manifest contains no tasks")
    if manifest["task_tag"].isna().any() or not manifest["task_tag"].is_unique:
        raise ValueError("Manifest task_tag values must be present and unique")
    cid = manifest["cid"].astype("string").str.strip()
    if (~cid.str.fullmatch(r"\d+")).any():
        raise ValueError("Manifest contains invalid cid values")
    if not (manifest["query"].astype("string") == "cid:" + cid).all():
        raise ValueError("Manifest query values must exactly match cid:<cid>")
    if set(manifest["priority"].astype(int)) != {1}:
        raise ValueError("This submission requires standard priority 1")


def load_submitted_tags(
    path: Path,
    manifest_tags: set[str] | None = None,
) -> set[str]:
    if not path.exists():
        return set()
    log = pd.read_csv(path, low_memory=False)
    required = {"task_tag", "submission_status"}
    missing = required - set(log.columns)
    if missing:
        raise KeyError(f"Task log is missing columns: {sorted(missing)}")
    submitted = set(
        log.loc[log["submission_status"].eq("submitted"), "task_tag"].astype(str)
    )
    if manifest_tags is not None:
        unexpected = submitted - manifest_tags
        if unexpected:
            raise ValueError(
                "Task log contains submitted tags outside this manifest: "
                f"{sorted(unexpected)[:3]}"
            )
    return submitted


def append_task_log(path: Path, records: list[dict[str, object]]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    additions = pd.DataFrame.from_records(records)
    if path.exists():
        existing = pd.read_csv(path, low_memory=False)
        columns = list(dict.fromkeys([*existing.columns, *additions.columns]))
        updated = pd.concat([existing, additions], ignore_index=True).reindex(
            columns=columns
        )
    else:
        updated = additions
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    updated.to_csv(temporary, index=False)
    temporary.replace(path)


def read_settings(path: Path) -> dict[str, object]:
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return content


def batches(records: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    return [
        records[index : index + MAXIMUM_BATCH_SIZE]
        for index in range(0, len(records), MAXIMUM_BATCH_SIZE)
    ]


def main() -> int:
    args = parse_arguments()
    manifest = pd.read_csv(args.manifest, dtype={"cid": "string"})
    validate_manifest(manifest)
    manifest_tags = set(manifest["task_tag"].astype(str))
    submitted_tags = load_submitted_tags(args.task_log, manifest_tags)
    remaining = manifest.loc[
        ~manifest["task_tag"].astype(str).isin(submitted_tags)
    ].copy()
    estimated_remaining_cost = round(
        float(remaining["estimated_unit_cost_usd"].sum()), 4
    )
    remaining_batches = batches(remaining.to_dict(orient="records"))
    confirmation_text = paid_confirmation_text(
        "BUSINESS_INFO", len(remaining)
    )
    validation_summary = {
        "manifest_rows": len(manifest),
        "previously_submitted_tasks": len(submitted_tags),
        "remaining_tasks": len(remaining),
        "remaining_post_batches": len(remaining_batches),
        "estimated_remaining_cost_usd": estimated_remaining_cost,
        "paid_submission_enabled": args.confirm_submit == confirmation_text,
        "required_confirmation_text": confirmation_text,
    }
    print(json.dumps(validation_summary, indent=2))

    if args.confirm_submit != confirmation_text:
        print("Validation only. No API requests were submitted.")
        return 0
    if remaining.empty:
        print("All manifest tasks were previously submitted.")
        return 0

    login, password = require_dataforseo_credentials()

    settings = read_settings(args.settings)
    dataforseo = settings.get("dataforseo")
    if not isinstance(dataforseo, dict):
        raise KeyError("settings.yaml is missing dataforseo")
    endpoints = dataforseo.get("endpoints")
    if not isinstance(endpoints, dict) or not endpoints.get("business_info_post"):
        raise KeyError("settings.yaml is missing business_info_post")
    endpoint = str(endpoints["business_info_post"])
    interval = float(dataforseo.get("request_interval_seconds", 1))
    client = DataForSEOClient(login, password)

    for batch_index, batch in enumerate(remaining_batches, start=1):
        try:
            records = client.submit_business_info_batch(url=endpoint, tasks=batch)
        except Exception as error:
            append_task_log(
                args.task_log,
                [
                    {
                        **row,
                        "submission_status": "failed",
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                    }
                    for row in batch
                ],
            )
            raise
        append_task_log(args.task_log, records)
        submitted = sum(
            record["submission_status"] == "submitted" for record in records
        )
        print(
            json.dumps(
                {
                    "batch": batch_index,
                    "batch_tasks": len(batch),
                    "submitted": submitted,
                    "failed": len(batch) - submitted,
                }
            )
        )
        if batch_index < len(remaining_batches):
            time.sleep(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
