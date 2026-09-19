"""Audit profile false positives and cross-group location splits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.location_resolution_audit import (
    audit_cross_group_locations,
    audit_profile_anomalies,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit unresolved profile and physical-location anomalies."
    )
    add_run_context_arguments(parser)
    parser.add_argument(
        "--review",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--profile-output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--location-output",
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
            "review": ("interim", "physical_location_group_review.csv"),
            "profile_output": ("interim", "profile_anomaly_review.csv"),
            "location_output": ("interim", "cross_group_location_review.csv"),
            "summary": ("interim", "location_resolution_audit_summary.json"),
        },
    )


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    review = pd.read_csv(
        args.review,
        dtype={"cid": "string", "zip": "string"},
        low_memory=False,
    )
    profile_anomalies = audit_profile_anomalies(review)
    location_pairs = audit_cross_group_locations(review)
    write_csv_atomic(profile_anomalies, args.profile_output)
    write_csv_atomic(location_pairs, args.location_output)

    profile_severity_counts = (
        {}
        if profile_anomalies.empty
        else {
            str(key): int(value)
            for key, value in profile_anomalies["anomaly_severity"]
            .value_counts().sort_index().items()
        }
    )
    location_groups = (
        set()
        if location_pairs.empty
        else set(location_pairs["left_location_group"])
        | set(location_pairs["right_location_group"])
    )
    summary = {
        "input_profiles": len(review),
        "input_location_groups": int(
            review["physical_location_group"].nunique()
        ),
        "profile_anomalies": len(profile_anomalies),
        "profile_anomalies_by_severity": profile_severity_counts,
        "cross_group_location_pairs": len(location_pairs),
        "location_groups_in_cross_group_pairs": len(location_groups),
        "automatic_exclusions": 0,
        "automatic_merges": 0,
        "profile_output": str(args.profile_output),
        "location_output": str(args.location_output),
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
