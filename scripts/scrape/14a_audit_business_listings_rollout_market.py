"""Audit one parsed rollout market against corrected legacy references."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.business_listings_comparison import (
    build_competition_unit_references,
    classify_competition_unit_reference_geography,
    match_reference_locations,
    prepare_pilot_candidates,
    summarize_rollout_market_comparison,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit one parsed rollout market without API calls."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--market", default="Atlanta_GA_L")
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument("--result-log", type=Path, default=None)
    parser.add_argument(
        "--reference-crosswalk",
        type=Path,
        default=Path(
            "outputs/diagnostics/corrected_v1/competition_units/"
            "competition_unit_crosswalk.csv"
        ),
    )
    parser.add_argument("--regions", type=Path, default=Path("config/regions.yaml"))
    parser.add_argument(
        "--category-rules",
        type=Path,
        default=Path("config/google_category_rules.csv"),
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
            "candidates": (
                "interim",
                "business_listings_rollout_market_parse/"
                "business_listings_rollout_candidates.csv",
            ),
            "result_log": (
                "raw",
                "business_listings_rollout/"
                "business_listings_rollout_result_log.csv",
            ),
            "output_directory": (
                "interim",
                "business_listings_rollout_market_comparison",
            ),
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
    market = str(args.market).strip()
    output_paths = {
        "eligibility": args.output_directory / "business_listings_rollout_eligibility.csv",
        "matches": args.output_directory / "business_listings_rollout_reference_matches.csv",
        "pairs": args.output_directory / "business_listings_rollout_reference_match_pairs.csv",
        "reference_universe": args.output_directory / "business_listings_rollout_reference_universe.csv",
        "market_recall": args.output_directory / "business_listings_rollout_market_recall.csv",
        "summary": args.output_directory / "business_listings_rollout_comparison_summary.json",
    }
    existing = [path for path in output_paths.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    candidates = pd.read_csv(
        args.candidates,
        dtype={"cid": "string", "place_id": "string", "zip": "string"},
        low_memory=False,
    )
    reference = pd.read_csv(
        args.reference_crosswalk,
        dtype={"clinic_key": "string", "zip": "string"},
        low_memory=False,
    )
    result_log = pd.read_csv(args.result_log, low_memory=False)
    regions_payload = read_yaml(args.regions)
    regions = regions_payload.get("regions")
    if not isinstance(regions, dict):
        raise KeyError("regions.yaml is missing regions")
    category_rules = pd.read_csv(args.category_rules, low_memory=False)
    plan = read_yaml(args.plan_config)
    pilot = plan.get("business_listings_pilot")
    rollout = plan.get("business_listings_rollout")
    if not isinstance(pilot, dict) or not isinstance(pilot.get("recall_gate"), dict):
        raise KeyError("scrape_plans.yaml is missing the frozen recall gate")
    if not isinstance(rollout, dict):
        raise KeyError("scrape_plans.yaml is missing business_listings_rollout")
    if str(rollout.get("large_market_validation_market", "")) != market:
        raise ValueError("Selected market is not the frozen large-market validation market")

    reviewed = prepare_pilot_candidates(
        candidates,
        regions,
        category_rules,
        target_markets={market},
    )
    unit_references = build_competition_unit_references(
        reference,
        target_markets={market},
    )
    reference_universe = classify_competition_unit_reference_geography(
        unit_references,
        regions,
        target_markets={market},
    )
    eligible_references = reference_universe.loc[
        reference_universe["reference_geography_status"].eq("eligible_target_zip")
    ].copy()
    matches, pairs = match_reference_locations(
        reviewed,
        eligible_references,
        reference_key_prefix=None,
        target_markets={market},
    )
    market_recall, summary = summarize_rollout_market_comparison(
        reviewed,
        matches,
        pilot["recall_gate"],
        result_log,
        market=market,
        reference_universe=reference_universe,
    )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(reviewed, output_paths["eligibility"])
    write_csv_atomic(matches, output_paths["matches"])
    write_csv_atomic(pairs, output_paths["pairs"])
    write_csv_atomic(reference_universe, output_paths["reference_universe"])
    write_csv_atomic(market_recall, output_paths["market_recall"])
    temporary = output_paths["summary"].with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(output_paths["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
