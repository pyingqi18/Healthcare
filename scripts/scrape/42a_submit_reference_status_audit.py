"""Validate or submit the frozen historical-reference status audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.reference_status_audit_execution import (
    submitted_reference_status_tasks,
    validate_reference_status_audit_manifest,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)
from medical_ratings.scrape_safety import paid_confirmation_text


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or submit the targeted historical-reference audit."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--plan-summary", type=Path, default=None)
    parser.add_argument("--task-log", type=Path, default=None)
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--confirm-submit", default=None)
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
        },
    )


def _write_log(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = pd.DataFrame.from_records(records)
    old = pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
    columns = list(dict.fromkeys([*old.columns, *new.columns]))
    combined = pd.concat([old, new], ignore_index=True).reindex(columns=columns)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    combined.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    plan_summary = json.loads(args.plan_summary.read_text(encoding="utf-8"))
    manifest = validate_reference_status_audit_manifest(
        pd.read_csv(args.manifest, low_memory=False), plan_summary
    )
    submitted: set[str] = set()
    if args.task_log.exists():
        submitted_frame = submitted_reference_status_tasks(
            pd.read_csv(args.task_log, low_memory=False), manifest
        )
        submitted = set(submitted_frame["task_tag"])
    remaining = manifest.loc[~manifest["task_tag"].isin(submitted)].copy()
    confirmation = paid_confirmation_text(
        "REFERENCE_STATUS_AUDIT", len(remaining)
    )
    summary = {
        "analysis_status": "reference_status_audit_submission_gate",
        "manifest_tasks": len(manifest),
        "audit_markets": sorted(set(manifest["market"])),
        "previously_submitted_tasks": len(submitted),
        "remaining_paid_tasks": len(remaining),
        "estimated_remaining_cost_usd": round(
            float(remaining["estimated_cost_usd"].sum()), 6
        ),
        "included_in_main_discovery_pipeline": False,
        "required_confirmation_text": confirmation,
        "paid_submission_enabled": args.confirm_submit == confirmation,
        "credentials_read": False,
        "api_requests_submitted": 0,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.confirm_submit != confirmation or remaining.empty:
        print("Validation only. No credentials were read and no API task was submitted.")
        return 0

    from medical_ratings.config import require_dataforseo_credentials
    from medical_ratings.dataforseo import DataForSEOClient

    login, password = require_dataforseo_credentials()
    settings = yaml.safe_load(args.settings.read_text(encoding="utf-8"))
    client = DataForSEOClient(login, password)
    records = client.submit_search_batch(
        url=str(settings["dataforseo"]["endpoints"]["maps_post"]),
        tasks=remaining.to_dict(orient="records"),
        api_type="maps_reference_status_audit",
    )
    _write_log(args.task_log, records)
    failed = sum(row["submission_status"] != "submitted" for row in records)
    print(
        json.dumps(
            {
                "execution_completed": failed == 0,
                "credentials_read": True,
                "http_post_requests_sent": 1,
                "tasks_submitted": len(records) - failed,
                "tasks_failed": failed,
                "included_in_main_discovery_pipeline": False,
                "task_log": str(args.task_log),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
