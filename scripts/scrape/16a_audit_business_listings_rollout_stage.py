"""Audit every parsed market in one Business Listings rollout stage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from medical_ratings.business_listings_comparison import (
    build_competition_unit_references,
    classify_competition_unit_reference_geography,
    match_reference_locations,
    prepare_pilot_candidates,
    summarize_rollout_market_comparison,
)
from medical_ratings.business_listings_pilot import evaluate_pilot_recall
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit all parsed markets in one rollout stage without API calls."
        )
    )
    add_run_context_arguments(parser)
    parser.add_argument("--stage", default="standard_rollout")
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
                "business_listings_rollout_stage_parse/standard_rollout/"
                "business_listings_rollout_stage_candidates.csv",
            ),
            "result_log": (
                "raw",
                "business_listings_rollout/"
                "business_listings_rollout_result_log.csv",
            ),
            "output_directory": (
                "interim",
                "business_listings_rollout_stage_comparison",
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


def write_json_atomic(payload: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def select_stage_markets(
    candidates: pd.DataFrame,
    result_log: pd.DataFrame,
    *,
    stage: str,
) -> list[str]:
    """Validate and return the markets represented by one completed stage."""

    candidate_required = {"requested_location", "profile_key"}
    missing_candidates = candidate_required - set(candidates.columns)
    if missing_candidates:
        raise KeyError(f"Candidates are missing: {sorted(missing_candidates)}")
    log_required = {"task_tag", "stage", "market", "request_status"}
    missing_log = log_required - set(result_log.columns)
    if missing_log:
        raise KeyError(f"Rollout result log is missing: {sorted(missing_log)}")

    completed = result_log.loc[
        result_log["stage"].astype(str).eq(stage)
        & result_log["request_status"].astype(str).eq("completed")
    ].copy()
    if completed.empty:
        raise ValueError(f"No completed requests found for stage: {stage}")
    if completed["task_tag"].astype(str).duplicated().any():
        raise ValueError("Rollout result log contains duplicate completed task tags")
    log_markets = set(completed["market"].dropna().astype(str))
    candidate_markets = set(candidates["requested_location"].dropna().astype(str))
    if log_markets != candidate_markets:
        raise ValueError(
            "Candidate markets differ from completed stage markets: "
            f"candidates={sorted(candidate_markets)}, log={sorted(log_markets)}"
        )
    if stage == "standard_rollout" and len(log_markets) != 10:
        raise ValueError("standard_rollout audit requires exactly ten markets")
    duplicated = candidates.duplicated(
        ["requested_location", "profile_key"], keep=False
    )
    if duplicated.any():
        raise ValueError("Candidates contain duplicate profile keys within a market")
    return sorted(log_markets)


def build_stage_summary(
    market_summaries: pd.DataFrame,
    reference_matches: pd.DataFrame,
    recall_gate: Mapping[str, Any],
    *,
    stage: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build a weighted stage-level recall summary from market results."""

    stage_recall, recall_summary = evaluate_pilot_recall(
        reference_matches[["reference_key", "market", "discovered"]].copy(),
        recall_gate,
    )
    summary = {
        "analysis_status": (
            "rollout_stage_comparison_before_manual_location_resolution"
        ),
        "stage": stage,
        "markets_audited": len(market_summaries),
        "completed_paid_requests": int(
            market_summaries["completed_paid_requests"].sum()
        ),
        "actual_api_cost_usd": round(
            float(market_summaries["actual_api_cost_usd"].sum()), 6
        ),
        "raw_items_reported": int(market_summaries["raw_items_reported"].sum()),
        "unique_profile_candidates_within_markets": int(
            market_summaries["unique_profile_candidates"].sum()
        ),
        "eligible_target_zip_profiles": int(
            market_summaries["eligible_target_zip_profiles"].sum()
        ),
        "outside_target_zip_profiles": int(
            market_summaries["outside_target_zip_profiles"].sum()
        ),
        "missing_zip_profiles": int(
            market_summaries["missing_zip_profiles"].sum()
        ),
        "non_us_postal_profiles": int(
            market_summaries["non_us_postal_profiles"].sum()
        ),
        "unrecognized_postal_profiles": int(
            market_summaries["unrecognized_postal_profiles"].sum()
        ),
        "provisional_included_profiles": int(
            market_summaries["provisional_included_profiles"].sum()
        ),
        "manual_category_review_profiles": int(
            market_summaries["manual_category_review_profiles"].sum()
        ),
        "excluded_category_profiles": int(
            market_summaries["excluded_category_profiles"].sum()
        ),
        "reference_recall": recall_summary,
        "markets_by_decision": {
            str(key): int(value)
            for key, value in market_summaries["decision"].value_counts().items()
        },
        "automatic_profile_or_location_merges": 0,
        "api_requests_submitted": 0,
        "interpretation_limit": (
            "Stage recall is weighted by corrected legacy reference locations. "
            "New profiles are not yet resolved into physical competition locations."
        ),
    }
    return stage_recall, summary


def main() -> int:
    args = parse_arguments()
    stage = str(args.stage).strip()
    if not stage:
        raise ValueError("stage cannot be blank")
    stage_directory = args.output_directory / stage
    summary_path = stage_directory / "business_listings_rollout_stage_comparison_summary.json"
    if summary_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output already exists: {summary_path}. Use --overwrite to replace it."
        )

    candidates = pd.read_csv(
        args.candidates,
        dtype={"cid": "string", "place_id": "string", "zip": "string"},
        low_memory=False,
    )
    result_log = pd.read_csv(args.result_log, low_memory=False)
    reference = pd.read_csv(
        args.reference_crosswalk,
        dtype={"clinic_key": "string", "zip": "string"},
        low_memory=False,
    )
    markets = select_stage_markets(candidates, result_log, stage=stage)

    regions_payload = read_yaml(args.regions)
    regions = regions_payload.get("regions")
    if not isinstance(regions, dict):
        raise KeyError("regions.yaml is missing regions")
    category_rules = pd.read_csv(args.category_rules, low_memory=False)
    plan = read_yaml(args.plan_config)
    pilot = plan.get("business_listings_pilot")
    if not isinstance(pilot, dict) or not isinstance(pilot.get("recall_gate"), dict):
        raise KeyError("scrape_plans.yaml is missing the frozen recall gate")
    recall_gate = pilot["recall_gate"]

    reviewed_frames: list[pd.DataFrame] = []
    match_frames: list[pd.DataFrame] = []
    pair_frames: list[pd.DataFrame] = []
    universe_frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    for market in markets:
        market_candidates = candidates.loc[
            candidates["requested_location"].astype(str).eq(market)
        ].copy()
        reviewed = prepare_pilot_candidates(
            market_candidates,
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
            reference_universe["reference_geography_status"].eq(
                "eligible_target_zip"
            )
        ].copy()
        matches, pairs = match_reference_locations(
            reviewed,
            eligible_references,
            reference_key_prefix=None,
            target_markets={market},
        )
        market_recall, market_summary = summarize_rollout_market_comparison(
            reviewed,
            matches,
            recall_gate,
            result_log,
            market=market,
            reference_universe=reference_universe,
        )

        market_directory = stage_directory / market
        write_csv_atomic(
            reviewed,
            market_directory / "business_listings_rollout_eligibility.csv",
        )
        write_csv_atomic(
            matches,
            market_directory / "business_listings_rollout_reference_matches.csv",
        )
        write_csv_atomic(
            pairs,
            market_directory / "business_listings_rollout_reference_match_pairs.csv",
        )
        write_csv_atomic(
            reference_universe,
            market_directory / "business_listings_rollout_reference_universe.csv",
        )
        write_csv_atomic(
            market_recall,
            market_directory / "business_listings_rollout_market_recall.csv",
        )
        write_json_atomic(
            market_summary,
            market_directory / "business_listings_rollout_comparison_summary.json",
        )

        recall = market_summary["reference_recall"]
        universe = market_summary["legacy_reference_universe"]
        summary_rows.append(
            {
                "market": market,
                "completed_paid_requests": market_summary["completed_paid_requests"],
                "actual_api_cost_usd": market_summary["actual_api_cost_usd"],
                "raw_items_reported": market_summary["raw_items_reported"],
                "unique_profile_candidates": market_summary[
                    "unique_profile_candidates"
                ],
                "eligible_target_zip_profiles": market_summary[
                    "eligible_target_zip_profiles"
                ],
                "outside_target_zip_profiles": market_summary[
                    "outside_target_zip_profiles"
                ],
                "missing_zip_profiles": market_summary["missing_zip_profiles"],
                "non_us_postal_profiles": market_summary[
                    "non_us_postal_profiles"
                ],
                "unrecognized_postal_profiles": market_summary[
                    "unrecognized_postal_profiles"
                ],
                "provisional_included_profiles": market_summary[
                    "provisional_included_profiles"
                ],
                "manual_category_review_profiles": market_summary[
                    "manual_category_review_profiles"
                ],
                "excluded_category_profiles": market_summary[
                    "excluded_category_profiles"
                ],
                "reference_count": recall["reference_count"],
                "discovered_count": recall["discovered_count"],
                "reference_recall": recall["overall_recall"],
                "unmatched_reference_locations": market_summary[
                    "unmatched_reference_locations"
                ],
                "decision": market_summary["decision"],
                "all_legacy_units_labeled_as_market": universe[
                    "all_competition_units_labeled_as_market"
                ],
                "eligible_target_zip_legacy_units": universe[
                    "eligible_target_zip_units"
                ],
                "outside_target_zip_legacy_units": universe[
                    "outside_target_zip_units"
                ],
                "missing_zip_legacy_units": universe["missing_zip_units"],
            }
        )
        reviewed_frames.append(reviewed)
        match_frames.append(matches)
        pair_frames.append(pairs)
        universe_frames.append(reference_universe)

    combined_reviewed = pd.concat(reviewed_frames, ignore_index=True)
    combined_matches = pd.concat(match_frames, ignore_index=True)
    combined_pairs = pd.concat(pair_frames, ignore_index=True)
    combined_universe = pd.concat(universe_frames, ignore_index=True)
    market_summaries = pd.DataFrame.from_records(summary_rows)
    stage_recall, stage_summary = build_stage_summary(
        market_summaries,
        combined_matches,
        recall_gate,
        stage=stage,
    )

    write_csv_atomic(
        combined_reviewed,
        stage_directory / "business_listings_rollout_stage_eligibility.csv",
    )
    write_csv_atomic(
        combined_matches,
        stage_directory / "business_listings_rollout_stage_reference_matches.csv",
    )
    write_csv_atomic(
        combined_pairs,
        stage_directory / "business_listings_rollout_stage_reference_match_pairs.csv",
    )
    write_csv_atomic(
        combined_universe,
        stage_directory / "business_listings_rollout_stage_reference_universe.csv",
    )
    write_csv_atomic(
        stage_recall,
        stage_directory / "business_listings_rollout_stage_recall.csv",
    )
    write_csv_atomic(
        market_summaries,
        stage_directory / "business_listings_rollout_stage_market_comparison.csv",
    )
    write_json_atomic(stage_summary, summary_path)
    print(json.dumps(stage_summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
