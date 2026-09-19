"""Recalculate all-market source-union recall after exact manual decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.adjudicated_source_union import (
    apply_adjudication_to_source_union,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recalculate source-union recall without API requests."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--source-union", type=Path, default=None)
    parser.add_argument("--reviewed-candidates", type=Path, default=None)
    parser.add_argument(
        "--plan-config", type=Path, default=Path("config/scrape_plans.yaml")
    )
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
            "reviewed_candidates": (
                "interim",
                "identity_rule_adjudication/identity_rule_reviewed_candidates.csv",
            ),
            "output_directory": (
                "interim",
                "adjudicated_source_union",
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
        "union": args.output_directory / "adjudicated_reference_source_union.csv",
        "market": args.output_directory / "adjudicated_source_union_by_market.csv",
        "remaining": args.output_directory / "remaining_unmatched_current_references.csv",
        "summary": args.output_directory / "adjudicated_source_union_summary.json",
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
    adjusted, by_market, summary = apply_adjudication_to_source_union(
        pd.read_csv(args.source_union, low_memory=False),
        pd.read_csv(args.reviewed_candidates, low_memory=False),
        expected_markets=markets,
        primary_market_minimum=float(gate["approve_primary_each_market_minimum"]),
        reject_market_below=float(gate["reject_each_market_below"]),
    )
    remaining = adjusted.loc[
        adjusted["current_reference_included"]
        & ~adjusted["source_union_discovered"]
    ].copy()
    write_csv_atomic(adjusted, outputs["union"])
    write_csv_atomic(by_market, outputs["market"])
    write_csv_atomic(remaining, outputs["remaining"])
    write_json_atomic(summary, outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(by_market.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
