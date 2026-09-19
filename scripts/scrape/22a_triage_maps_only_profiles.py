"""Triage true Maps-only profiles and cross-source identity evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.maps_only_review import (
    build_maps_business_identity_pairs,
    combine_business_listings_profiles,
    summarize_maps_only_review,
    triage_maps_profile_review,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Triage Maps-only profiles without API calls or automatic decisions."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--stage", default="standard_rollout")
    parser.add_argument("--profile-audit", type=Path, default=None)
    parser.add_argument("--pilot-adjudicated", type=Path, default=None)
    parser.add_argument("--atlanta-eligibility", type=Path, default=None)
    parser.add_argument("--standard-eligibility", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    stage = str(args.stage).strip()
    return resolve_run_context_arguments(
        args,
        {
            "profile_audit": (
                "interim",
                f"maps_standard_supplement_audit/{stage}/maps_core_profile_audit.csv",
            ),
            "pilot_adjudicated": (
                "interim",
                "business_listings_pilot_manual_audit/"
                "business_listings_adjudicated_candidates.csv",
            ),
            "atlanta_eligibility": (
                "interim",
                "business_listings_rollout_market_comparison/"
                "business_listings_rollout_eligibility.csv",
            ),
            "standard_eligibility": (
                "interim",
                "business_listings_rollout_stage_comparison/standard_rollout/"
                "business_listings_rollout_stage_eligibility.csv",
            ),
            "output_directory": (
                "interim",
                f"maps_only_profile_triage/{stage}",
            ),
        },
    )


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def write_json_atomic(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    outputs = {
        "triage": args.output_directory / "maps_only_profile_triage.csv",
        "uncovered": args.output_directory / "maps_uncovered_market_profiles.csv",
        "pairs": args.output_directory / "maps_business_identity_review_pairs.csv",
        "market": args.output_directory / "maps_only_triage_by_market.csv",
        "summary": args.output_directory / "maps_only_triage_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    profile_audit = pd.read_csv(
        args.profile_audit,
        dtype={"cid": "string", "place_id": "string", "zip": "string"},
        low_memory=False,
    )
    triaged = triage_maps_profile_review(profile_audit)
    business = combine_business_listings_profiles(
        [
            (
                "pilot_adjudicated",
                pd.read_csv(args.pilot_adjudicated, low_memory=False),
            ),
            (
                "atlanta_provisional",
                pd.read_csv(args.atlanta_eligibility, low_memory=False),
            ),
            (
                "standard_rollout_provisional",
                pd.read_csv(args.standard_eligibility, low_memory=False),
            ),
        ]
    )
    pairs = build_maps_business_identity_pairs(triaged, business)
    summary = summarize_maps_only_review(triaged, pairs)

    true_maps_only = triaged.loc[
        ~triaged["maps_review_queue"].isin(
            {
                "already_seen_in_business_listings",
                "await_business_listings_primary",
            }
        )
    ].copy()
    uncovered = triaged.loc[
        triaged["maps_review_queue"].eq("await_business_listings_primary")
    ].copy()
    market_summary = (
        true_maps_only.groupby(
            ["requested_location", "maps_review_queue"], sort=True
        )
        .size()
        .unstack(fill_value=0)
        .reset_index()
        .rename(columns={"requested_location": "market"})
    )

    write_csv_atomic(true_maps_only, outputs["triage"])
    write_csv_atomic(uncovered, outputs["uncovered"])
    write_csv_atomic(pairs, outputs["pairs"])
    write_csv_atomic(market_summary, outputs["market"])
    write_json_atomic(summary, outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
