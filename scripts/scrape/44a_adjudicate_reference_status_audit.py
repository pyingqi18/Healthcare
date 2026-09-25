"""Parse and manually adjudicate the targeted reference-status audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from medical_ratings.reference_status_adjudication import (
    apply_reference_status_decisions,
    build_reference_status_decision_template,
    build_reference_status_evidence,
    parse_reference_status_results,
)
from medical_ratings.reference_status_audit_execution import (
    validate_reference_status_audit_manifest,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Parse the 50 saved historical-reference queries, prepare one manual "
            "decision file, and optionally apply completed decisions without "
            "adding targeted results to the main discovery numerator."
        )
    )
    add_run_context_arguments(parser)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--plan-summary", type=Path, default=None)
    parser.add_argument("--task-log", type=Path, default=None)
    parser.add_argument("--raw-directory", type=Path, default=None)
    parser.add_argument("--inventory", type=Path, default=None)
    parser.add_argument("--source-union", type=Path, default=None)
    parser.add_argument("--decisions", type=Path, default=None)
    parser.add_argument(
        "--plan-config", type=Path, default=Path("config/scrape_plans.yaml")
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "manifest": (
                "interim",
                "post_adjudication_completion_plan/reference_status_audit_manifest.csv",
            ),
            "plan_summary": (
                "interim",
                "post_adjudication_completion_plan/"
                "post_adjudication_completion_summary.json",
            ),
            "task_log": (
                "raw",
                "reference_status_audit/reference_status_audit_task_log.csv",
            ),
            "raw_directory": ("raw", "reference_status_audit/raw"),
            "inventory": (
                "interim",
                "post_adjudication_completion_plan/remaining_reference_inventory.csv",
            ),
            "source_union": (
                "interim",
                "maps_specialist_followup_adjudication/"
                "source_union_after_followup_adjudication.csv",
            ),
            "output_directory": (
                "interim",
                "reference_status_audit_adjudication",
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
    preparation_paths = {
        "observations": args.output_directory / "reference_status_observations.csv",
        "pairs": args.output_directory / "reference_status_candidate_evidence.csv",
        "evidence": args.output_directory / "reference_status_reference_evidence.csv",
        "template": args.output_directory / "reference_status_decisions.csv",
        "summary": args.output_directory / "reference_status_preparation_summary.json",
    }
    applied_paths = {
        "decisions": args.output_directory / "validated_reference_status_decisions.csv",
        "union": args.output_directory / "source_union_after_reference_status_audit.csv",
        "markets": args.output_directory / "reference_status_audit_by_market.csv",
        "summary": args.output_directory / "reference_status_adjudication_summary.json",
    }
    paths = list(preparation_paths.values())
    if args.decisions is not None:
        paths.extend(applied_paths.values())
    _check_outputs(paths, args.overwrite)

    plan_summary = json.loads(args.plan_summary.read_text(encoding="utf-8"))
    manifest = validate_reference_status_audit_manifest(
        pd.read_csv(args.manifest, low_memory=False), plan_summary
    )
    observations = parse_reference_status_results(
        manifest,
        pd.read_csv(args.task_log, low_memory=False),
        args.raw_directory,
    )
    pairs, evidence, summary = build_reference_status_evidence(
        manifest,
        pd.read_csv(args.inventory, low_memory=False),
        observations,
    )
    template = build_reference_status_decision_template(evidence)
    if args.decisions is None:
        summary["next_required_action"] = (
            "Review all 50 rows in reference_status_decisions.csv, fill the manual "
            "decision and reviewer evidence fields, then rerun this script with "
            "--decisions."
        )
    _write_csv(observations, preparation_paths["observations"])
    _write_csv(pairs, preparation_paths["pairs"])
    _write_csv(evidence, preparation_paths["evidence"])
    if args.decisions is None or not preparation_paths["template"].exists():
        _write_csv(template, preparation_paths["template"])
    _write_json(summary, preparation_paths["summary"])

    if args.decisions is None:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    plan = yaml.safe_load(args.plan_config.read_text(encoding="utf-8"))
    gate = _mapping(
        _mapping(plan.get("business_listings_pilot"), "business_listings_pilot").get(
            "recall_gate"
        ),
        "recall_gate",
    )
    reviewed, union, by_market, applied_summary = apply_reference_status_decisions(
        template,
        pd.read_csv(args.decisions, low_memory=False, keep_default_na=False),
        pairs,
        pd.read_csv(args.source_union, low_memory=False),
        primary_market_minimum=float(gate["approve_primary_each_market_minimum"]),
        reject_market_below=float(gate["reject_each_market_below"]),
    )
    _write_csv(reviewed, applied_paths["decisions"])
    _write_csv(union, applied_paths["union"])
    _write_csv(by_market, applied_paths["markets"])
    _write_json(applied_summary, applied_paths["summary"])
    print(json.dumps(applied_summary, indent=2, ensure_ascii=False))
    print(by_market.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
