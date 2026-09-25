"""Check readiness or download the frozen reference-status audit tasks."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.reference_status_audit_execution import (
    pending_reference_status_tasks,
    submitted_reference_status_tasks,
    validate_reference_status_audit_manifest,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check readiness or download targeted reference-status results."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--plan-summary", type=Path, default=None)
    parser.add_argument("--task-log", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--download-ready", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "manifest": (
                "interim",
                "post_adjudication_completion_plan/"
                "reference_status_audit_manifest.csv",
            ),
            "plan_summary": (
                "interim",
                "post_adjudication_completion_plan/"
                "post_adjudication_completion_summary.json",
            ),
            "task_log": (
                "raw",
                "reference_status_audit/reference_status_audit_task_log.csv",
            ),
            "output_directory": (
                "raw",
                "reference_status_audit/raw",
            ),
        },
    )


def _payload_tag(payload: Mapping[str, object]) -> str | None:
    tasks = payload.get("tasks") or []
    if len(tasks) != 1 or not isinstance(tasks[0], Mapping):
        return None
    data = tasks[0].get("data") or {}
    if not isinstance(data, Mapping) or data.get("tag") is None:
        return None
    return str(data["tag"])


def main() -> int:
    args = parse_arguments()
    plan_summary = json.loads(args.plan_summary.read_text(encoding="utf-8"))
    manifest = validate_reference_status_audit_manifest(
        pd.read_csv(args.manifest, low_memory=False), plan_summary
    )
    submitted = submitted_reference_status_tasks(
        pd.read_csv(args.task_log, low_memory=False), manifest
    )
    if len(submitted) != len(manifest):
        raise ValueError(
            "All frozen reference-status tasks must be submitted before download"
        )
    pending = pending_reference_status_tasks(submitted, args.output_directory)
    if not args.download_ready:
        print(
            json.dumps(
                {
                    "analysis_status": "reference_status_audit_download_gate",
                    "manifest_tasks": len(manifest),
                    "submitted_tasks": len(submitted),
                    "already_downloaded": len(submitted) - len(pending),
                    "remaining_tasks": len(pending),
                    "download_enabled": False,
                    "credentials_read": False,
                    "api_requests_submitted": 0,
                },
                indent=2,
            )
        )
        return 0

    from medical_ratings.config import require_dataforseo_credentials
    from medical_ratings.dataforseo import DataForSEOClient

    login, password = require_dataforseo_credentials()
    endpoints = yaml.safe_load(args.settings.read_text(encoding="utf-8"))[
        "dataforseo"
    ]["endpoints"]
    client = DataForSEOClient(login, password)
    ready = client.get_ready_task_ids(str(endpoints["maps_tasks_ready"]))
    ready_rows = pending.loc[pending["task_id"].isin(ready)].copy()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for row in ready_rows.itertuples(index=False):
        payload = client.get_task(str(endpoints["maps_get"]), str(row.task_id))
        if _payload_tag(payload) != str(row.task_tag):
            raise ValueError(f"Downloaded task tag mismatch: {row.task_tag}")
        target = args.output_directory / f"{row.task_id}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temporary.replace(target)
    remaining = len(pending) - len(ready_rows)
    print(
        json.dumps(
            {
                "execution_completed": remaining == 0,
                "credentials_read": True,
                "tasks_ready": len(ready_rows),
                "tasks_not_ready": remaining,
                "results_downloaded": len(ready_rows),
                "tasks_ready_checks": 1,
                "result_get_requests": len(ready_rows),
                "automatic_premature_get_requests": 0,
                "remaining_after_download": remaining,
                "raw_directory": str(args.output_directory),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
