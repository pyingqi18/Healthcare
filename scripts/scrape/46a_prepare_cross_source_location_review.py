"""Prepare profile decisions or build 15-market physical-location review blocks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from medical_ratings.cross_source_profile_resolution import (
    apply_profile_decisions_and_build_location_review,
    build_cross_source_profile_review,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Unify exact Google profiles across all discovery sources, prepare one "
            "manual eligibility file, and optionally build scalable location blocks."
        )
    )
    add_run_context_arguments(parser)
    parser.add_argument("--business-profiles", type=Path, default=None)
    parser.add_argument("--core-maps-profiles", type=Path, default=None)
    parser.add_argument("--specialist-profiles", type=Path, default=None)
    parser.add_argument("--reviewed-specialist-profiles", type=Path, default=None)
    parser.add_argument("--carry-forward", type=Path, default=None)
    parser.add_argument("--reference-universe", type=Path, default=None)
    parser.add_argument(
        "--prior-profile-decisions",
        type=Path,
        default=Path("config/candidate_manual_decisions_20260908.csv"),
    )
    parser.add_argument(
        "--category-rules",
        type=Path,
        default=Path("config/google_category_rules.csv"),
    )
    parser.add_argument("--decisions", type=Path, default=None)
    parser.add_argument("--plan-config", type=Path, default=Path("config/scrape_plans.yaml"))
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "business_profiles": (
                "interim",
                "all_market_source_audit/all_market_business_listings_eligibility.csv",
            ),
            "core_maps_profiles": (
                "interim",
                "maps_standard_supplement_audit/standard_rollout/"
                "maps_core_profile_audit.csv",
            ),
            "specialist_profiles": (
                "interim",
                "maps_specialist_source_union_audit/maps_specialist_profile_audit.csv",
            ),
            "reviewed_specialist_profiles": (
                "interim",
                "maps_specialist_followup_adjudication/"
                "adjudicated_specialist_profiles.csv",
            ),
            "carry_forward": (
                "interim",
                "primary_discovery_benchmark_freeze/"
                "validated_legacy_carry_forward_inventory.csv",
            ),
            "reference_universe": (
                "interim",
                "all_market_source_audit/"
                "all_market_fused_historical_reference_universe.csv",
            ),
            "output_directory": (
                "interim",
                "cross_source_profile_location_review",
            ),
        },
    )


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype={
            "profile_key": "string",
            "clinic_key": "string",
            "cid": "string",
            "place_id": "string",
            "reference_key": "string",
            "subject_key": "string",
        },
        low_memory=False,
    )


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _check_outputs(paths: list[Path], overwrite: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )


def main() -> int:
    args = parse_arguments()
    plan = yaml.safe_load(args.plan_config.read_text(encoding="utf-8"))
    expected_markets = set(
        plan["profiles"]["existing_15_markets_planning_v1"]["markets"]
    )
    inputs = [
        args.business_profiles,
        args.core_maps_profiles,
        args.specialist_profiles,
        args.reviewed_specialist_profiles,
        args.carry_forward,
        args.reference_universe,
        args.prior_profile_decisions,
        args.category_rules,
    ]
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing cross-source inputs: " + ", ".join(missing))

    inventory, template, anchors, lineage, preparation = (
        build_cross_source_profile_review(
            _read(args.business_profiles),
            _read(args.core_maps_profiles),
            _read(args.specialist_profiles),
            _read(args.reviewed_specialist_profiles),
            _read(args.carry_forward),
            _read(args.reference_universe),
            expected_markets=expected_markets,
            prior_manual_profile_decisions=_read(args.prior_profile_decisions),
            category_rules=_read(args.category_rules),
        )
    )
    preparation_outputs = {
        "inventory": args.output_directory / "unified_cross_source_profile_inventory.csv",
        "template": args.output_directory / "profile_eligibility_decisions.csv",
        "anchors": args.output_directory / "legacy_carry_forward_location_anchors.csv",
        "lineage": args.output_directory / "legacy_carry_forward_outcome_lineage.csv",
        "summary": args.output_directory / "cross_source_profile_preparation_summary.json",
    }
    if args.decisions is None:
        _check_outputs(list(preparation_outputs.values()), args.overwrite)
        _write_csv(inventory, preparation_outputs["inventory"])
        _write_csv(template, preparation_outputs["template"])
        _write_csv(anchors, preparation_outputs["anchors"])
        _write_csv(lineage, preparation_outputs["lineage"])
        _write_json(preparation, preparation_outputs["summary"])
        print(json.dumps(preparation, ensure_ascii=False, indent=2))
        return 0

    applied_outputs = {
        "decisions": args.output_directory / "validated_profile_eligibility_decisions.csv",
        "all_profiles": args.output_directory / "adjudicated_cross_source_profiles.csv",
        "included": args.output_directory / "included_outcome_profiles.csv",
        "pairs": args.output_directory / "physical_location_candidate_pairs.csv",
        "blocks": args.output_directory / "physical_location_review_blocks.csv",
        "triage": args.output_directory / "physical_location_block_triage.csv",
        "block_profiles": args.output_directory / "physical_location_block_profiles.csv",
        "summary": args.output_directory / "cross_source_location_review_summary.json",
    }
    _check_outputs(list(applied_outputs.values()), args.overwrite)
    if not args.decisions.exists():
        raise FileNotFoundError(f"Profile decisions do not exist: {args.decisions}")
    outputs = apply_profile_decisions_and_build_location_review(
        inventory,
        template,
        _read(args.decisions),
        anchors,
    )
    reviewed, profiles, included, pairs, blocks, triage, block_profiles, summary = outputs
    _write_csv(reviewed, applied_outputs["decisions"])
    _write_csv(profiles, applied_outputs["all_profiles"])
    _write_csv(included, applied_outputs["included"])
    _write_csv(pairs, applied_outputs["pairs"])
    _write_csv(blocks, applied_outputs["blocks"])
    _write_csv(triage, applied_outputs["triage"])
    _write_csv(block_profiles, applied_outputs["block_profiles"])
    _write_json(summary, applied_outputs["summary"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
