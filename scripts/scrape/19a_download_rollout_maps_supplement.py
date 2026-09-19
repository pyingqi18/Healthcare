"""Download only Maps Standard tasks reported complete by Tasks Ready."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.config import require_dataforseo_credentials
from medical_ratings.dataforseo import DataForSEOClient
from medical_ratings.scrape_run_context import add_run_context_arguments, resolve_run_context_arguments


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check readiness or download completed Maps supplement tasks.")
    add_run_context_arguments(parser)
    parser.add_argument("--stage", default="standard_rollout")
    parser.add_argument("--task-log", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--download-ready", action="store_true")
    args = parser.parse_args()
    stage = str(args.stage).strip()
    return resolve_run_context_arguments(args, {
        "task_log": ("raw", f"maps_standard_supplement/{stage}/maps_standard_task_log.csv"),
        "output_directory": ("raw", f"maps_standard_supplement/{stage}/raw"),
    })


def main() -> int:
    args = parse_arguments()
    log = pd.read_csv(args.task_log, low_memory=False)
    submitted = log.loc[log["submission_status"].eq("submitted")].drop_duplicates("task_tag", keep="last").copy()
    if submitted.empty or submitted["task_id"].isna().any():
        raise ValueError("Task log contains no complete submitted task set")
    saved = {path.stem for path in args.output_directory.glob("*.json")}
    pending = submitted.loc[~submitted["task_id"].astype(str).isin(saved)].copy()
    if not args.download_ready:
        print(json.dumps({"submitted_tasks": len(submitted), "already_downloaded": len(submitted) - len(pending), "remaining_tasks": len(pending), "download_enabled": False, "credentials_read": False, "api_requests_submitted": 0}, indent=2))
        return 0
    login, password = require_dataforseo_credentials()
    settings = yaml.safe_load(args.settings.read_text(encoding="utf-8"))["dataforseo"]
    client = DataForSEOClient(login, password)
    ready = client.get_ready_task_ids(str(settings["endpoints"]["maps_tasks_ready"]))
    ready_rows = pending.loc[pending["task_id"].astype(str).isin(ready)]
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for row in ready_rows.itertuples(index=False):
        payload = client.get_task(str(settings["endpoints"]["maps_get"]), str(row.task_id))
        target = args.output_directory / f"{row.task_id}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(target)
    print(json.dumps({"submitted_tasks": len(submitted), "tasks_ready": len(ready_rows), "tasks_not_ready": len(pending) - len(ready_rows), "results_downloaded": len(ready_rows), "tasks_ready_checks": 1, "result_get_requests": len(ready_rows), "automatic_premature_get_requests": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
