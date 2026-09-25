"""Prepare grouped review aids for the remaining cross-source profile decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.profile_eligibility_triage import (
    prepare_profile_eligibility_triage,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Group unresolved profile eligibility decisions using frozen category "
            "rules and title evidence without applying final decisions."
        )
    )
    add_run_context_arguments(parser)
    parser.add_argument("--decisions", type=Path, default=None)
    parser.add_argument("--inventory", type=Path, default=None)
    parser.add_argument(
        "--category-rules",
        type=Path,
        default=Path("config/google_category_rules.csv"),
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "decisions": (
                "interim",
                "cross_source_profile_location_review/profile_eligibility_decisions.csv",
            ),
            "inventory": (
                "interim",
                "cross_source_profile_location_review/unified_cross_source_profile_inventory.csv",
            ),
            "output_directory": (
                "interim",
                "profile_eligibility_triage",
            ),
        },
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


def main() -> int:
    args = parse_arguments()
    inputs = [args.decisions, args.inventory, args.category_rules]
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing profile triage inputs: " + ", ".join(missing))
    outputs = {
        "triage": args.output_directory / "profile_eligibility_triage.csv",
        "groups": args.output_directory / "profile_eligibility_category_groups.csv",
        "unknown": args.output_directory / "unknown_category_rule_candidates.csv",
        "summary": args.output_directory / "profile_eligibility_triage_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )
    triage, groups, unknown, summary = prepare_profile_eligibility_triage(
        pd.read_csv(args.decisions, dtype=str, keep_default_na=False, low_memory=False),
        pd.read_csv(args.inventory, dtype=str, keep_default_na=False, low_memory=False),
        pd.read_csv(args.category_rules, dtype=str, keep_default_na=False),
    )
    _write_csv(triage, outputs["triage"])
    _write_csv(groups, outputs["groups"])
    _write_csv(unknown, outputs["unknown"])
    _write_json(summary, outputs["summary"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
