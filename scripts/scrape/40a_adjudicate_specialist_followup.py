"""Prepare or apply one consolidated specialist follow-up decision file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)
from medical_ratings.specialist_followup_adjudication import (
    apply_specialist_followup_decisions,
    build_specialist_followup_decision_template,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare one specialist decision file or apply its completed decisions."
        )
    )
    add_run_context_arguments(parser)
    parser.add_argument("--identity-queue", type=Path, default=None)
    parser.add_argument("--profile-queue", type=Path, default=None)
    parser.add_argument("--profile-audit", type=Path, default=None)
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
            "identity_queue": (
                "interim",
                "maps_specialist_followup_review/specialist_identity_review_queue.csv",
            ),
            "profile_queue": (
                "interim",
                "maps_specialist_followup_review/specialist_profile_review_queue.csv",
            ),
            "profile_audit": (
                "interim",
                "maps_specialist_source_union_audit/maps_specialist_profile_audit.csv",
            ),
            "source_union": (
                "interim",
                "maps_specialist_source_union_audit/source_union_after_specialist.csv",
            ),
            "output_directory": (
                "interim",
                "maps_specialist_followup_adjudication",
            ),
        },
    )


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype={
            "candidate_cid": "string",
            "cid": "string",
            "place_id": "string",
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
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    identity = _read(args.identity_queue)
    profiles = _read(args.profile_queue)
    template, preparation = build_specialist_followup_decision_template(
        identity, profiles, _read(args.profile_audit)
    )
    if args.decisions is None:
        outputs = {
            "template": args.output_directory / "specialist_followup_decisions.csv",
            "summary": args.output_directory / "specialist_followup_preparation_summary.json",
        }
        existing = [path for path in outputs.values() if path.exists()]
        if existing and not args.overwrite:
            raise FileExistsError(
                "Output already exists: "
                + ", ".join(str(path) for path in existing)
                + ". Use --overwrite to replace it."
            )
        _write_csv(template, outputs["template"])
        _write_json(preparation, outputs["summary"])
        print(json.dumps(preparation, indent=2, ensure_ascii=False))
        return 0

    outputs = {
        "reviewed": args.output_directory / "validated_specialist_followup_decisions.csv",
        "confirmed": args.output_directory / "confirmed_specialist_identity_matches.csv",
        "profiles": args.output_directory / "adjudicated_specialist_profiles.csv",
        "union": args.output_directory / "source_union_after_followup_adjudication.csv",
        "markets": args.output_directory / "source_union_after_followup_by_market.csv",
        "summary": args.output_directory / "specialist_followup_adjudication_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )
    plan = yaml.safe_load(args.plan_config.read_text(encoding="utf-8"))
    gate = plan["business_listings_pilot"]["recall_gate"]
    reviewed, confirmed, profile, union, markets, summary = (
        apply_specialist_followup_decisions(
            template,
            _read(args.decisions),
            identity,
            _read(args.source_union),
            primary_market_minimum=float(
                gate["approve_primary_each_market_minimum"]
            ),
            reject_market_below=float(gate["reject_each_market_below"]),
        )
    )
    _write_csv(reviewed, outputs["reviewed"])
    _write_csv(confirmed, outputs["confirmed"])
    _write_csv(profile, outputs["profiles"])
    _write_csv(union, outputs["union"])
    _write_csv(markets, outputs["markets"])
    _write_json(summary, outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(markets.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
