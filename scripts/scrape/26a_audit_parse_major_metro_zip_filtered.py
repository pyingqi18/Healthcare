"""Audit and parse completed ZIP-filtered LA and NYC token pages offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.major_metro_filtered_parse import (
    audit_and_parse_major_metro_filtered_pages,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit and parse complete ZIP-filtered major-metro pages offline."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--page-plan", type=Path, default=None)
    parser.add_argument("--page-log", type=Path, default=None)
    parser.add_argument("--raw-directory", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "page_plan": (
                "interim",
                "business_listings_major_metro_zip_filtered/"
                "major_metro_zip_filtered_page_plan.csv",
            ),
            "page_log": (
                "raw",
                "business_listings_major_metro_zip_filtered/"
                "major_metro_zip_filtered_page_log.csv",
            ),
            "raw_directory": (
                "raw",
                "business_listings_major_metro_zip_filtered/raw",
            ),
            "output_directory": (
                "interim",
                "business_listings_major_metro_zip_filtered_parse",
            ),
        },
    )


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def write_json_atomic(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    observations, candidates, group_audit, market_summary, summary = (
        audit_and_parse_major_metro_filtered_pages(
            pd.read_csv(args.page_log, low_memory=False),
            pd.read_csv(args.page_plan, low_memory=False),
            args.raw_directory,
        )
    )
    write_csv_atomic(
        observations,
        args.output_directory / "major_metro_zip_filtered_observations.csv",
    )
    write_csv_atomic(
        candidates,
        args.output_directory / "major_metro_zip_filtered_candidates.csv",
    )
    write_csv_atomic(
        group_audit,
        args.output_directory / "major_metro_zip_filtered_group_audit.csv",
    )
    write_csv_atomic(
        market_summary,
        args.output_directory / "major_metro_zip_filtered_market_summary.csv",
    )
    write_json_atomic(
        summary,
        args.output_directory / "major_metro_zip_filtered_parse_summary.json",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(market_summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
