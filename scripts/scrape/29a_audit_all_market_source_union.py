"""Audit marginal and union historical-reference recall across 15 markets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)
from medical_ratings.source_union_audit import (
    build_reference_source_union,
    summarize_reference_source_union,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute 15-market source union recall without API requests."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--business-matches", type=Path, default=None)
    parser.add_argument("--maps-matches", type=Path, default=None)
    parser.add_argument(
        "--plan-config", type=Path, default=Path("config/scrape_plans.yaml")
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "business_matches": (
                "interim",
                "all_market_source_audit/"
                "all_market_business_listings_reference_matches.csv",
            ),
            "maps_matches": (
                "interim",
                "all_market_source_audit/"
                "all_market_maps_standard_reference_matches.csv",
            ),
            "output_directory": (
                "interim",
                "all_market_source_union_audit",
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
        "union": args.output_directory / "all_market_reference_source_union.csv",
        "market": args.output_directory / "all_market_source_union_by_market.csv",
        "unmatched": args.output_directory / "all_market_reference_unmatched_by_both.csv",
        "maps_incremental": args.output_directory / "all_market_reference_maps_incremental.csv",
        "summary": args.output_directory / "all_market_source_union_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )
    plan = yaml.safe_load(args.plan_config.read_text(encoding="utf-8"))
    profile = plan["profiles"]["existing_15_markets_planning_v1"]
    markets = {str(value) for value in profile["markets"]}
    if len(markets) != 15:
        raise ValueError("Frozen planning profile must contain 15 unique markets")
    gate = plan["business_listings_pilot"]["recall_gate"]
    primary_minimum = float(gate["approve_primary_each_market_minimum"])
    reject_below = float(gate["reject_each_market_below"])
    business = pd.read_csv(args.business_matches, low_memory=False)
    maps = pd.read_csv(args.maps_matches, low_memory=False)
    union = build_reference_source_union(
        business, maps, expected_markets=markets
    )
    by_market, summary = summarize_reference_source_union(
        union,
        expected_markets=markets,
        primary_market_minimum=primary_minimum,
        reject_market_below=reject_below,
    )
    unmatched = union.loc[
        union["source_discovery_status"].eq("not_discovered_by_either")
    ].copy()
    incremental = union.loc[
        union["source_discovery_status"].eq("maps_incremental")
    ].copy()
    write_csv_atomic(union, outputs["union"])
    write_csv_atomic(by_market, outputs["market"])
    write_csv_atomic(unmatched, outputs["unmatched"])
    write_csv_atomic(incremental, outputs["maps_incremental"])
    write_json_atomic(summary, outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(by_market.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
