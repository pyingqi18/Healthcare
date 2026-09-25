"""Plan remaining reference review and uniform residual discovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from medical_ratings.post_adjudication_completion import (
    build_post_adjudication_completion_plan,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plan below-gate reference review and one conditional uniform residual "
            "Maps discovery tier without API calls."
        )
    )
    add_run_context_arguments(parser)
    parser.add_argument("--source-union", type=Path, default=None)
    parser.add_argument("--reviewed-decisions", type=Path, default=None)
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
                "maps_specialist_followup_adjudication/"
                "source_union_after_followup_adjudication.csv",
            ),
            "reviewed_decisions": (
                "interim",
                "maps_specialist_followup_adjudication/"
                "validated_specialist_followup_decisions.csv",
            ),
            "output_directory": (
                "interim",
                "post_adjudication_completion_plan",
            ),
        },
    )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    outputs = {
        "markets": args.output_directory / "market_completion_plan.csv",
        "remaining": args.output_directory / "remaining_reference_inventory.csv",
        "audit": args.output_directory / "reference_status_audit_manifest.csv",
        "residual": args.output_directory / "uniform_residual_keyword_manifest.csv",
        "unresolved": args.output_directory / "unresolved_followup_decisions.csv",
        "summary": args.output_directory / "post_adjudication_completion_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    plan = yaml.safe_load(args.plan_config.read_text(encoding="utf-8"))
    profile = _mapping(
        _mapping(plan.get("profiles"), "profiles").get(
            "existing_15_markets_planning_v1"
        ),
        "existing_15_markets_planning_v1",
    )
    phases = profile.get("phases")
    if not isinstance(phases, list):
        raise TypeError("Planning profile phases must be a list")
    phase = next(
        (
            value
            for value in phases
            if isinstance(value, Mapping)
            and value.get("phase_id") == "maps_residual_singleton_redesign"
        ),
        None,
    )
    if not isinstance(phase, Mapping):
        raise KeyError("Planning profile lacks maps_residual_singleton_redesign")
    regions_payload = yaml.safe_load(args.regions.read_text(encoding="utf-8"))
    regions = _mapping(regions_payload.get("regions"), "regions")
    pricing = _mapping(plan.get("pricing"), "pricing")
    gate = _mapping(
        _mapping(plan.get("business_listings_pilot"), "business_listings_pilot").get(
            "recall_gate"
        ),
        "recall_gate",
    )

    outputs_data = build_post_adjudication_completion_plan(
        pd.read_csv(args.source_union, low_memory=False),
        pd.read_csv(args.reference_crosswalk, low_memory=False),
        pd.read_csv(args.reviewed_decisions, low_memory=False),
        markets=profile["markets"],
        regions=regions,
        residual_keywords=phase["keywords"],
        primary_market_minimum=float(gate["approve_primary_each_market_minimum"]),
        reject_market_below=float(gate["reject_each_market_below"]),
        maps_price_per_100_results_usd=float(
            pricing["google_maps_standard_per_100_results"]
        ),
    )
    markets, remaining, audit, residual, unresolved, summary = outputs_data
    summary["pricing_verified_on"] = str(pricing.get("verified_on"))
    _write_csv(markets, outputs["markets"])
    _write_csv(remaining, outputs["remaining"])
    _write_csv(audit, outputs["audit"])
    _write_csv(residual, outputs["residual"])
    _write_csv(unresolved, outputs["unresolved"])
    _write_json(summary, outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    below_gate = markets.loc[
        markets["next_action"].ne("freeze_primary_discovery")
    ]
    print(below_gate.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
