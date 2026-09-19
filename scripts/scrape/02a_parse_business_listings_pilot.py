"""Parse and deduplicate raw Business Listings pilot responses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.business_listings_live import (
    deduplicate_business_listings,
    parse_business_listings_payload,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse the raw Business Listings pilot without API calls."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--results-directory", type=Path, default=None)
    parser.add_argument("--observations-output", type=Path, default=None)
    parser.add_argument("--candidates-output", type=Path, default=None)
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "results_directory": ("raw", "business_listings_pilot"),
            "observations_output": ("interim", "business_listings_pilot_observations.csv"),
            "candidates_output": ("interim", "business_listings_pilot_candidates.csv"),
        },
    )


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def parse_completed_results(log: pd.DataFrame, raw_directory: Path) -> pd.DataFrame:
    required = {
        "task_tag",
        "market",
        "request_status",
        "raw_file",
        "retrieved_at_utc",
        "item_count",
    }
    missing = required - set(log.columns)
    if missing:
        raise KeyError(f"Pilot result log is missing columns: {sorted(missing)}")
    completed = (
        log.loc[log["request_status"].eq("completed")]
        .drop_duplicates("task_tag", keep="last")
        .copy()
    )
    if len(completed) != 4:
        raise ValueError("Parser requires all four completed pilot requests")
    records: list[dict[str, object]] = []
    expected = 0
    for row in completed.to_dict(orient="records"):
        raw_path = raw_directory / str(row["raw_file"])
        if not raw_path.is_file():
            raise FileNotFoundError(f"Missing raw Business Listings response: {raw_path}")
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        parsed = parse_business_listings_payload(
            payload,
            expected_tag=str(row["task_tag"]),
            market=str(row["market"]),
            retrieved_at_utc=str(row["retrieved_at_utc"]),
        )
        records.extend(parsed)
        expected += int(row["item_count"])
    if len(records) != expected:
        raise ValueError(
            f"Parsed item count differs from result log: parsed={len(records)}, expected={expected}"
        )
    if not records:
        raise ValueError("All four Business Listings requests returned zero items")
    return pd.DataFrame.from_records(records)


def main() -> int:
    args = parse_arguments()
    log_path = args.results_directory / "business_listings_result_log.csv"
    log = pd.read_csv(log_path, low_memory=False)
    observations = parse_completed_results(log, args.results_directory / "raw")
    candidates = deduplicate_business_listings(observations)
    write_csv_atomic(observations, args.observations_output)
    write_csv_atomic(candidates, args.candidates_output)
    print(
        json.dumps(
            {
                "parsed_observations": len(observations),
                "unique_profile_candidates": len(candidates),
                "duplicate_observations_removed": len(observations) - len(candidates),
                "markets": sorted(candidates["requested_location"].unique()),
                "api_requests_submitted": 0,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
