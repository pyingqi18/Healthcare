"""Validate or submit final-location Google Reviews tasks in safe batches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import pandas as pd
import yaml

from medical_ratings.config import require_dataforseo_credentials
from medical_ratings.dataforseo import DataForSEOClient
from medical_ratings.scrape_safety import paid_confirmation_text
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


API_MAXIMUM_BATCH_SIZE = 100
REQUIRED_COLUMNS = {
    "task_tag",
    "final_physical_location_id",
    "clinic_key",
    "cid",
    "place_id",
    "identifier_type",
    "identifier_value",
    "requested_location",
    "location_code",
    "language_code",
    "sort_by",
    "planned_depth",
    "estimated_maximum_cost_usd",
}
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or submit paid Google Reviews tasks."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--settings", type=Path, default=Path("config/settings.yaml")
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
            "manifest": ("interim", "review_collection_manifest.csv"),
            "task_log": ("raw", "review_task_log.csv"),
        },
    )


def validate_manifest(manifest: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(manifest.columns)
    if missing:
        raise KeyError(f"Manifest is missing columns: {sorted(missing)}")
    if manifest.empty:
        raise ValueError("Manifest contains no tasks")
    for column in (
        "task_tag",
        "final_physical_location_id",
        "clinic_key",
        "cid",
        "identifier_type",
        "identifier_value",
        "requested_location",
    ):
        values = manifest[column].astype("string").str.strip()
        if values.isna().any() or values.eq("").any():
            raise ValueError(f"Manifest contains blank {column} values")
    for column in ("task_tag", "clinic_key", "identifier_value"):
        if manifest[column].duplicated().any():
            raise ValueError(f"Manifest contains duplicate {column} values")

    if "outcome_profile_key" in manifest.columns:
        profile_keys = manifest["outcome_profile_key"].astype("string").str.strip()
        if profile_keys.isna().any() or profile_keys.eq("").any():
            raise ValueError("Manifest contains blank outcome_profile_key values")
        if profile_keys.duplicated().any():
            raise ValueError("Manifest contains duplicate outcome_profile_key values")
    if "competition_location_id" in manifest.columns:
        location_ids = manifest["competition_location_id"].astype("string").str.strip()
        if location_ids.isna().any() or location_ids.eq("").any():
            raise ValueError("Manifest contains blank competition_location_id values")
        aliases = manifest["final_physical_location_id"].astype("string").str.strip()
        if not location_ids.eq(aliases).all():
            raise ValueError(
                "competition_location_id does not match the compatibility alias"
            )

    identifier_types = set(manifest["identifier_type"].astype(str))
    if not identifier_types.issubset({"place_id", "cid"}):
        raise ValueError("Manifest contains invalid identifier types")
    for row in manifest.itertuples(index=False):
        expected = row.place_id if row.identifier_type == "place_id" else row.cid
        if str(row.identifier_value).strip() != str(expected).strip():
            raise ValueError(
                f"Identifier value does not match source field for {row.task_tag}"
            )

    depth = pd.to_numeric(manifest["planned_depth"], errors="coerce")
    if depth.isna().any() or not depth.between(1, 4490).all():
        raise ValueError("Manifest contains invalid review depth values")
    if depth.mod(10).ne(0).any():
        raise ValueError("Manifest review depths must be multiples of ten")
    costs = pd.to_numeric(
        manifest["estimated_maximum_cost_usd"], errors="coerce"
    )
    if costs.isna().any() or costs.lt(0).any():
        raise ValueError("Manifest contains invalid cost estimates")


def load_submitted_tags(path: Path, manifest_tags: set[str]) -> set[str]:
    if not path.exists():
        return set()
    log = pd.read_csv(path, low_memory=False)
    required = {"task_tag", "submission_status"}
    missing = required - set(log.columns)
    if missing:
        raise KeyError(f"Task log is missing columns: {sorted(missing)}")
    submitted = set(
        log.loc[log["submission_status"].eq("submitted"), "task_tag"]
        .astype(str)
        .str.strip()
    )
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


def batches(
    records: list[dict[str, object]], batch_size: int
) -> list[list[dict[str, object]]]:
    if not 1 <= batch_size <= API_MAXIMUM_BATCH_SIZE:
        raise ValueError("Review batch size must be between 1 and 100")
    return [
        records[index : index + batch_size]
        for index in range(0, len(records), batch_size)
    ]


def read_settings(path: Path) -> dict[str, object]:
    settings = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return settings


def main() -> int:
    args = parse_arguments()
    manifest = pd.read_csv(
        args.manifest,
        dtype={"cid": "string", "place_id": "string"},
        low_memory=False,
    )
    validate_manifest(manifest)
    settings = read_settings(args.settings)
    dataforseo = settings.get("dataforseo")
    if not isinstance(dataforseo, dict):
        raise KeyError("settings.yaml is missing dataforseo")
    batch_size = int(dataforseo.get("review_task_batch_size", 50))

    manifest_tags = set(manifest["task_tag"].astype(str).str.strip())
    submitted_tags = load_submitted_tags(args.task_log, manifest_tags)
    remaining = manifest.loc[
        ~manifest["task_tag"].astype(str).isin(submitted_tags)
    ].copy()
    remaining_batches = batches(
        remaining.to_dict(orient="records"), batch_size
    )
    confirmation_text = paid_confirmation_text("REVIEW", len(remaining))
    summary = {
        "manifest_rows": len(manifest),
        "previously_submitted_tasks": len(submitted_tags),
        "remaining_tasks": len(remaining),
        "remaining_post_batches": len(remaining_batches),
        "estimated_remaining_maximum_cost_usd": round(
            float(remaining["estimated_maximum_cost_usd"].sum()), 4
        ),
        "paid_submission_enabled": args.confirm_submit == confirmation_text,
        "required_confirmation_text": confirmation_text,
    }
    print(json.dumps(summary, indent=2))

    if args.confirm_submit != confirmation_text:
        print("Validation only. No API requests were submitted.")
        return 0
    if remaining.empty:
        print("All manifest tasks were previously submitted.")
        return 0

    login, password = require_dataforseo_credentials()
    endpoints = dataforseo.get("endpoints")
    if not isinstance(endpoints, dict) or not endpoints.get("reviews_post"):
        raise KeyError("settings.yaml is missing reviews_post")
    endpoint = str(endpoints["reviews_post"])
    interval = float(dataforseo.get("request_interval_seconds", 1))
    client = DataForSEOClient(login, password)

    for batch_index, batch in enumerate(remaining_batches, start=1):
        try:
            records = client.submit_review_batch(url=endpoint, tasks=batch)
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
