"""Write a planning-only 15-market discovery and cost comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from medical_ratings.scrape_plan import build_scrape_profile_plan
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan a full-market search profile without API execution."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--plan-config",
        type=Path,
        default=Path("config/scrape_plans.yaml"),
    )
    parser.add_argument(
        "--regions",
        type=Path,
        default=Path("config/regions.yaml"),
    )
    parser.add_argument(
        "--profile",
        default="existing_15_markets_planning_v1",
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {"output_directory": ("interim", "search_profile_plan")},
    )


def read_yaml(path: Path) -> dict[str, object]:
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return content


def main() -> None:
    args = parse_arguments()
    plan, summary = build_scrape_profile_plan(
        read_yaml(args.plan_config),
        read_yaml(args.regions),
        profile_name=args.profile,
    )
    plan_path = args.output_directory / "search_profile_plan.csv"
    summary_path = args.output_directory / "search_profile_summary.json"
    existing = [path for path in (plan_path, summary_path) if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    plan.to_csv(plan_path, index=False)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
