"""Validate or submit the frozen 75-task Maps specialist supplement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.maps_specialist_plan import validate_specialist_manifest
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)
from medical_ratings.scrape_safety import paid_confirmation_text


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or submit the uniform Maps specialist supplement."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--task-log", type=Path, default=None)
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument(
        "--plan-config", type=Path, default=Path("config/scrape_plans.yaml")
    )
    parser.add_argument("--confirm-submit", default=None)
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "manifest": (
                "interim",
                "maps_specialist_supplement_plan/maps_specialist_manifest.csv",
            ),
            "task_log": (
                "raw",
                "maps_specialist_supplement/maps_specialist_task_log.csv",
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
    manifest = pd.read_csv(args.manifest, low_memory=False)
    plan = yaml.safe_load(args.plan_config.read_text(encoding="utf-8"))
    profile = plan["profiles"]["existing_15_markets_planning_v1"]
    phase = next(
        value
        for value in profile["phases"]
        if value["phase_id"] == "maps_specialist_keyword_supplement"
    )
    expected_markets = {str(value) for value in profile["markets"]}
    expected_keywords = {str(value) for value in phase["keywords"]}
    validate_specialist_manifest(
        manifest,
        expected_markets=expected_markets,
        expected_keywords=expected_keywords,
    )

    submitted: set[str] = set()
    if args.task_log.exists():
        log = pd.read_csv(args.task_log, low_memory=False)
        submitted = set(
            log.loc[log["submission_status"].eq("submitted"), "task_tag"].astype(str)
        )
        unexpected = submitted - set(manifest["task_tag"].astype(str))
        if unexpected:
            raise ValueError(
                f"Specialist task log contains unexpected tags: {sorted(unexpected)}"
            )
    remaining = manifest.loc[
        ~manifest["task_tag"].astype(str).isin(submitted)
    ].copy()
    confirmation = paid_confirmation_text("MAPS_SPECIALIST", len(remaining))
    summary = {
        "manifest_tasks": len(manifest),
        "previously_submitted_tasks": len(submitted),
        "remaining_paid_tasks": len(remaining),
        "http_post_batches": 0 if remaining.empty else 1,
        "required_confirmation_text": confirmation,
        "paid_submission_enabled": args.confirm_submit == confirmation,
        "credentials_read": False,
        "api_requests_submitted": 0,
    }
    print(json.dumps(summary, indent=2))
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
        api_type="maps_specialist",
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
                "task_log": str(args.task_log),
            },
            indent=2,
        )
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
