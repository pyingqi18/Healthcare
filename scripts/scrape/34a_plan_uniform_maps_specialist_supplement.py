"""Plan the frozen five-keyword Maps specialist tier without API calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from medical_ratings.maps_specialist_plan import build_specialist_manifest
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan a uniform five-keyword Maps specialist supplement."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--benchmark", type=Path, default=None)
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
            "benchmark": (
                "interim",
                "adjudicated_source_union/adjudicated_source_union_by_market.csv",
            ),
            "output_directory": (
                "interim",
                "maps_specialist_supplement_plan",
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
    manifest_path = args.output_directory / "maps_specialist_manifest.csv"
    summary_path = args.output_directory / "maps_specialist_plan_summary.json"
    existing = [path for path in (manifest_path, summary_path) if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    plan = yaml.safe_load(args.plan_config.read_text(encoding="utf-8"))
    regions_payload = yaml.safe_load(args.regions.read_text(encoding="utf-8"))
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
            and value.get("phase_id") == "maps_specialist_keyword_supplement"
        ),
        None,
    )
    if not isinstance(phase, Mapping):
        raise KeyError("Planning profile lacks maps_specialist_keyword_supplement")
    markets = profile.get("markets")
    keywords = phase.get("keywords")
    if not isinstance(markets, list) or not isinstance(keywords, list):
        raise TypeError("Specialist markets and keywords must be lists")
    pricing = _mapping(plan.get("pricing"), "pricing")
    regions = _mapping(regions_payload.get("regions"), "regions")
    manifest, summary = build_specialist_manifest(
        pd.read_csv(args.benchmark, low_memory=False),
        markets=markets,
        keywords=keywords,
        regions=regions,
        price_per_100_results_usd=float(
            pricing["google_maps_standard_per_100_results"]
        ),
    )
    summary["pricing_verified_on"] = str(pricing.get("verified_on"))
    summary["manifest"] = str(manifest_path)
    _write_csv(manifest, manifest_path)
    _write_json(summary, summary_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
