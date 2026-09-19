"""Audit pilot ZIP/category eligibility and corrected-reference recall."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.business_listings_comparison import (
    match_reference_locations,
    prepare_pilot_candidates,
    summarize_pilot_comparison,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Business Listings pilot candidates with corrected references."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument("--result-log", type=Path, default=None)
    parser.add_argument(
        "--reference-crosswalk",
        type=Path,
        default=Path(
            "outputs/diagnostics/corrected_v1/competition_units/competition_unit_crosswalk.csv"
        ),
    )
    parser.add_argument("--regions", type=Path, default=Path("config/regions.yaml"))
    parser.add_argument(
        "--category-rules", type=Path, default=Path("config/google_category_rules.csv")
    )
    parser.add_argument(
        "--plan-config", type=Path, default=Path("config/scrape_plans.yaml")
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "candidates": ("interim", "business_listings_pilot_candidates.csv"),
            "result_log": ("raw", "business_listings_pilot/business_listings_result_log.csv"),
            "output_directory": ("interim", "business_listings_pilot_comparison"),
        },
    )


def read_yaml(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return payload


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    output_paths = {
        "eligibility": args.output_directory / "business_listings_pilot_eligibility.csv",
        "matches": args.output_directory / "business_listings_reference_matches.csv",
        "pairs": args.output_directory / "business_listings_reference_match_pairs.csv",
        "market_recall": args.output_directory / "business_listings_market_recall.csv",
        "summary": args.output_directory / "business_listings_pilot_comparison_summary.json",
    }
    existing = [path for path in output_paths.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    candidates = pd.read_csv(
        args.candidates, dtype={"cid": "string", "place_id": "string", "zip": "string"}, low_memory=False
    )
    reference = pd.read_csv(
        args.reference_crosswalk, dtype={"clinic_key": "string", "zip": "string"}, low_memory=False
    )
    result_log = pd.read_csv(args.result_log, low_memory=False)
    regions_config = read_yaml(args.regions)
    regions = regions_config.get("regions")
    if not isinstance(regions, dict):
        raise KeyError("regions.yaml is missing regions")
    category_rules = pd.read_csv(args.category_rules, low_memory=False)
    plan = read_yaml(args.plan_config)
    pilot = plan.get("business_listings_pilot")
    if not isinstance(pilot, dict) or not isinstance(pilot.get("recall_gate"), dict):
        raise KeyError("scrape_plans.yaml is missing the pilot recall gate")

    reviewed = prepare_pilot_candidates(candidates, regions, category_rules)
    matches, pairs = match_reference_locations(
        reviewed,
        reference,
        reference_key_prefix=str(pilot.get("reference_key_prefix", "")),
    )
    market_recall, summary = summarize_pilot_comparison(
        reviewed, matches, pilot["recall_gate"], result_log
    )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(reviewed, output_paths["eligibility"])
    write_csv_atomic(matches, output_paths["matches"])
    write_csv_atomic(pairs, output_paths["pairs"])
    write_csv_atomic(market_recall, output_paths["market_recall"])
    temporary = output_paths["summary"].with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output_paths["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
