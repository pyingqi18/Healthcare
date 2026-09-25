"""Build specialist follow-up review queues and market-gap diagnostics."""

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
from medical_ratings.specialist_followup_audit import (
    build_market_gap_diagnostic,
    build_specialist_identity_review_queue,
    build_specialist_profile_review_queue,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build specialist manual-review queues and diagnose market recall gaps "
            "without API calls."
        )
    )
    add_run_context_arguments(parser)
    parser.add_argument("--profile-audit", type=Path, default=None)
    parser.add_argument("--exact-overlap", type=Path, default=None)
    parser.add_argument("--reference-match-pairs", type=Path, default=None)
    parser.add_argument("--remaining-references", type=Path, default=None)
    parser.add_argument("--market-summary", type=Path, default=None)
    parser.add_argument(
        "--plan-config", type=Path, default=Path("config/scrape_plans.yaml")
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    base = "maps_specialist_source_union_audit"
    return resolve_run_context_arguments(
        args,
        {
            "profile_audit": ("interim", f"{base}/maps_specialist_profile_audit.csv"),
            "exact_overlap": (
                "interim",
                f"{base}/maps_specialist_exact_source_overlap.csv",
            ),
            "reference_match_pairs": (
                "interim",
                f"{base}/maps_specialist_reference_match_pairs.csv",
            ),
            "remaining_references": (
                "interim",
                f"{base}/remaining_unmatched_after_specialist.csv",
            ),
            "market_summary": (
                "interim",
                f"{base}/source_union_after_specialist_by_market.csv",
            ),
            "output_directory": ("interim", "maps_specialist_followup_review"),
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
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype={"cid": "string", "candidate_cid": "string", "place_id": "string"},
        low_memory=False,
    )


def main() -> int:
    args = parse_arguments()
    outputs = {
        "identity": args.output_directory / "specialist_identity_review_queue.csv",
        "profiles": args.output_directory / "specialist_profile_review_queue.csv",
        "markets": args.output_directory / "market_coverage_gap_diagnostic.csv",
        "summary": args.output_directory / "specialist_followup_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    plan = yaml.safe_load(args.plan_config.read_text(encoding="utf-8"))
    profile = plan["profiles"]["existing_15_markets_planning_v1"]
    expected = {str(value) for value in profile["markets"]}
    gate = plan["business_listings_pilot"]["recall_gate"]

    remaining = _read_csv(args.remaining_references)
    identity = build_specialist_identity_review_queue(
        remaining, _read_csv(args.reference_match_pairs)
    )
    profiles = build_specialist_profile_review_queue(
        _read_csv(args.profile_audit), _read_csv(args.exact_overlap)
    )
    markets, summary = build_market_gap_diagnostic(
        _read_csv(args.market_summary),
        remaining,
        identity,
        profiles,
        expected_markets=expected,
        primary_market_minimum=float(
            gate["approve_primary_each_market_minimum"]
        ),
        reject_market_below=float(gate["reject_each_market_below"]),
    )
    _write_csv(identity, outputs["identity"])
    _write_csv(profiles, outputs["profiles"])
    _write_csv(markets, outputs["markets"])
    _write_json(summary, outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(
        markets.loc[
            markets["source_union_after_specialist_recall"].lt(
                float(gate["approve_primary_each_market_minimum"])
            )
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
