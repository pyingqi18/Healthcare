"""Build the offline review queue for historical units missed by both sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)
from medical_ratings.unmatched_reference_audit import (
    build_unmatched_reference_review,
    summarize_unmatched_reference_review,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Triage historical references missed by both discovery sources."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--source-union", type=Path, default=None)
    parser.add_argument("--reference-universe", type=Path, default=None)
    parser.add_argument("--business-matches", type=Path, default=None)
    parser.add_argument("--maps-matches", type=Path, default=None)
    parser.add_argument("--market-summary", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "source_union": (
                "interim",
                "all_market_source_union_audit/all_market_reference_source_union.csv",
            ),
            "reference_universe": (
                "interim",
                "all_market_source_audit/all_market_fused_historical_reference_universe.csv",
            ),
            "business_matches": (
                "interim",
                "all_market_source_audit/all_market_business_listings_reference_matches.csv",
            ),
            "maps_matches": (
                "interim",
                "all_market_source_audit/all_market_maps_standard_reference_matches.csv",
            ),
            "market_summary": (
                "interim",
                "all_market_source_union_audit/all_market_source_union_by_market.csv",
            ),
            "output_directory": (
                "interim",
                "all_market_unmatched_reference_review",
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
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    outputs = {
        "queue": args.output_directory / "unmatched_reference_review_queue.csv",
        "market": args.output_directory / "unmatched_reference_review_by_market.csv",
        "summary": args.output_directory / "unmatched_reference_review_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )
    review = build_unmatched_reference_review(
        pd.read_csv(args.source_union, low_memory=False),
        pd.read_csv(args.reference_universe, dtype={"zip": "string"}, low_memory=False),
        pd.read_csv(args.business_matches, low_memory=False),
        pd.read_csv(args.maps_matches, low_memory=False),
        pd.read_csv(args.market_summary, low_memory=False),
    )
    by_market, summary = summarize_unmatched_reference_review(review)
    write_csv_atomic(review, outputs["queue"])
    write_csv_atomic(by_market, outputs["market"])
    write_json_atomic(summary, outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(by_market.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
