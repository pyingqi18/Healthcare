"""Apply evidence-backed manual decisions to the Business Listings pilot audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.business_listings_manual_audit import (
    adjudicate_pilot_candidates,
    adjudicate_reference_locations,
    summarize_manual_audit,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply pilot manual evidence decisions.")
    add_run_context_arguments(parser)
    parser.add_argument("--eligibility", type=Path, default=None)
    parser.add_argument("--reference-matches", type=Path, default=None)
    parser.add_argument("--match-pairs", type=Path, default=None)
    parser.add_argument(
        "--candidate-decisions",
        type=Path,
        default=Path("config/business_listings_pilot_candidate_decisions_20260918.csv"),
    )
    parser.add_argument(
        "--reference-decisions",
        type=Path,
        default=Path("config/business_listings_pilot_reference_decisions_20260918.csv"),
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    return resolve_run_context_arguments(
        parser.parse_args(),
        {
            "eligibility": (
                "interim",
                "business_listings_pilot_comparison/business_listings_pilot_eligibility.csv",
            ),
            "reference_matches": (
                "interim",
                "business_listings_pilot_comparison/business_listings_reference_matches.csv",
            ),
            "match_pairs": (
                "interim",
                "business_listings_pilot_comparison/business_listings_reference_match_pairs.csv",
            ),
            "output_directory": ("interim", "business_listings_pilot_manual_audit"),
        },
    )


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    outputs = {
        "candidates": args.output_directory / "business_listings_adjudicated_candidates.csv",
        "references": args.output_directory / "business_listings_adjudicated_references.csv",
        "summary": args.output_directory / "business_listings_manual_audit_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    eligibility = pd.read_csv(args.eligibility, dtype={"cid": "string"}, low_memory=False)
    matches = pd.read_csv(args.reference_matches, low_memory=False)
    pairs = pd.read_csv(args.match_pairs, low_memory=False)
    candidate_decisions = pd.read_csv(args.candidate_decisions, low_memory=False)
    reference_decisions = pd.read_csv(args.reference_decisions, low_memory=False)
    candidates = adjudicate_pilot_candidates(eligibility, candidate_decisions)
    references = adjudicate_reference_locations(
        matches, pairs, candidates, reference_decisions
    )
    summary = summarize_manual_audit(candidates, references)

    args.output_directory.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(candidates, outputs["candidates"])
    write_csv_atomic(references, outputs["references"])
    temporary = outputs["summary"].with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(outputs["summary"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
