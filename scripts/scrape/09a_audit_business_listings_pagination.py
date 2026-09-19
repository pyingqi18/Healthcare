"""Audit saved Business Listings responses for omitted result pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.business_listings_live import (
    audit_business_listings_page_groups,
    business_listings_page_metadata,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit saved Business Listings pages without calling the API."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--result-log", type=Path, default=None)
    parser.add_argument("--raw-directory", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "result_log": (
                "raw",
                "business_listings_pilot/business_listings_result_log.csv",
            ),
            "raw_directory": ("raw", "business_listings_pilot/raw"),
            "output_directory": (
                "interim",
                "business_listings_pagination_audit",
            ),
        },
    )


def audit_saved_pages(result_log: pd.DataFrame, raw_directory: Path) -> pd.DataFrame:
    required = {"task_tag", "request_status", "raw_file", "market", "category_group"}
    missing = required - set(result_log.columns)
    if missing:
        raise KeyError(f"Business Listings result log is missing: {sorted(missing)}")
    completed = result_log.loc[result_log["request_status"].eq("completed")].copy()
    if completed.empty:
        raise ValueError("Business Listings result log has no completed requests")
    if completed["task_tag"].astype(str).duplicated().any():
        raise ValueError("Business Listings result log contains duplicate completed tags")

    rows: list[dict[str, object]] = []
    for record in completed.to_dict(orient="records"):
        raw_path = raw_directory / str(record["raw_file"])
        if not raw_path.is_file():
            raise FileNotFoundError(raw_path)
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        offset_value = record.get("offset", 0)
        offset = (
            0
            if pd.isna(offset_value) or str(offset_value).strip() == ""
            else int(offset_value)
        )
        metadata = business_listings_page_metadata(
            payload,
            expected_tag=str(record["task_tag"]),
            requested_offset=offset,
        )
        rows.append(
            {
                "task_tag": record["task_tag"],
                "market": record["market"],
                "category_group": record["category_group"],
                "raw_file": record["raw_file"],
                **metadata,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["market", "category_group", "requested_offset"], ignore_index=True
    )


def main() -> int:
    args = parse_arguments()
    pages = audit_saved_pages(
        pd.read_csv(args.result_log, low_memory=False),
        args.raw_directory,
    )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    pages.to_csv(
        args.output_directory / "business_listings_page_completeness.csv",
        index=False,
    )
    groups = audit_business_listings_page_groups(pages)
    groups.to_csv(
        args.output_directory / "business_listings_group_completeness.csv",
        index=False,
    )
    pages_reporting_more = pages.loc[pages["pagination_required"]]
    incomplete_groups = groups.loc[~groups["category_group_complete"]]
    summary = {
        "analysis_status": "saved_response_pagination_audit",
        "api_requests_submitted": 0,
        "completed_pages_audited": len(pages),
        "category_groups_audited": len(groups),
        "reported_total_items_across_category_groups": int(
            groups["reported_total_count"].sum()
        ),
        "returned_items_across_saved_pages": int(
            pages["returned_item_count"].sum()
        ),
        "pages_reporting_later_results": len(pages_reporting_more),
        "category_groups_requiring_continuation": len(incomplete_groups),
        "all_saved_category_groups_complete": incomplete_groups.empty,
        "incomplete_category_groups": [
            f"{row.market}:g{int(row.category_group):02d}"
            for row in incomplete_groups.itertuples(index=False)
        ],
        "interpretation": (
            "Earlier saved pages can report later results while the combined category "
            "group is complete. Completeness is based on contiguous saved offset "
            "coverage within each market and category group. No API request is made."
        ),
    }
    summary_path = args.output_directory / "business_listings_pagination_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
