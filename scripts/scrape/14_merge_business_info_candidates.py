"""Enrich all candidates and recompute geography and category review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.candidate_eligibility import (
    apply_candidate_eligibility_review,
)
from medical_ratings.candidate_enrichment import (
    enrich_candidates_with_business_info,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge Business Info profiles and recompute candidate review."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--candidates",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        default=None,
    )
    parser.add_argument("--regions", type=Path, default=Path("config/regions.yaml"))
    parser.add_argument(
        "--category-rules",
        type=Path,
        default=Path("config/google_category_rules.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "candidates": ("interim", "clinic_candidate_eligibility_review.csv"),
            "profiles": ("interim", "business_info_profiles.csv"),
            "output": ("interim", "clinic_candidates_enriched_review.csv"),
            "summary": ("interim", "clinic_candidates_enriched_summary.json"),
        },
    )


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    candidates = pd.read_csv(args.candidates, dtype={"cid": "string"}, low_memory=False)
    profiles = pd.read_csv(
        args.profiles,
        dtype={"cid": "string", "zip": "string"},
        low_memory=False,
    )
    region_config = yaml.safe_load(args.regions.read_text(encoding="utf-8"))
    regions = region_config.get("regions")
    if not isinstance(regions, dict):
        raise KeyError("regions.yaml is missing the regions mapping")
    category_rules = pd.read_csv(args.category_rules)

    enriched = enrich_candidates_with_business_info(candidates, profiles, regions)
    reviewed = apply_candidate_eligibility_review(enriched, category_rules)
    if len(reviewed) != len(candidates):
        raise ValueError("Candidate row count changed during enrichment")
    write_csv_atomic(reviewed, args.output)

    newly_located = reviewed.loc[
        reviewed["previous_market_assignment_status"].isin(
            {"local_finder_only_unlocated", "maps_missing_zip"}
        )
        & reviewed["market_assignment_status"].eq("eligible_target_zip")
    ]
    summary = {
        "input_candidates": len(candidates),
        "business_info_profiles": len(profiles),
        "output_candidates": len(reviewed),
        "unique_cid": int(reviewed["cid"].nunique()),
        "business_info_matched": int(reviewed["business_info_matched"].sum()),
        "newly_located_in_target_zip": len(newly_located),
        "newly_located_by_market": {
            str(key): int(value)
            for key, value in newly_located["mapped_location"]
            .value_counts()
            .sort_index()
            .items()
        },
        "market_assignment_status": {
            str(key): int(value)
            for key, value in reviewed["market_assignment_status"]
            .value_counts()
            .sort_index()
            .items()
        },
        "eligibility_review_status": {
            str(key): int(value)
            for key, value in reviewed["eligibility_review_status"]
            .value_counts()
            .sort_index()
            .items()
        },
        "output": str(args.output),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    temporary_summary = args.summary.with_suffix(f"{args.summary.suffix}.tmp")
    temporary_summary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_summary.replace(args.summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
