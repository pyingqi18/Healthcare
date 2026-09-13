"""Apply reviewed profile and physical-location decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.final_location_resolution import (
    apply_location_resolution_decisions,
)


DEFAULT_RUN_NAME = "rescrape_malone_syracuse_20260907"
DEFAULT_DIRECTORY = Path("data/interim") / DEFAULT_RUN_NAME


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze reviewed Google profiles into physical locations."
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        default=DEFAULT_DIRECTORY / "physical_location_group_review.csv",
    )
    parser.add_argument(
        "--anomalies",
        type=Path,
        default=DEFAULT_DIRECTORY / "profile_anomaly_review.csv",
    )
    parser.add_argument(
        "--location-pairs",
        type=Path,
        default=DEFAULT_DIRECTORY / "cross_group_location_review.csv",
    )
    parser.add_argument(
        "--profile-decisions",
        type=Path,
        default=Path("config/profile_resolution_decisions_20260910.csv"),
    )
    parser.add_argument(
        "--location-decisions",
        type=Path,
        default=Path("config/location_group_decisions_20260910.csv"),
    )
    parser.add_argument(
        "--crosswalk-output",
        type=Path,
        default=DEFAULT_DIRECTORY / "clinic_profile_location_crosswalk.csv",
    )
    parser.add_argument(
        "--location-output",
        type=Path,
        default=DEFAULT_DIRECTORY / "physical_dental_locations_final.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=DEFAULT_DIRECTORY / "final_location_resolution_summary.json",
    )
    return parser.parse_args()


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    profiles = pd.read_csv(args.profiles, dtype={"cid": "string"}, low_memory=False)
    anomalies = pd.read_csv(args.anomalies, dtype={"cid": "string"}, low_memory=False)
    profile_decisions = pd.read_csv(
        args.profile_decisions, dtype={"cid": "string"}, low_memory=False
    )
    location_pairs = pd.read_csv(args.location_pairs, low_memory=False)
    location_decisions = pd.read_csv(args.location_decisions, low_memory=False)
    crosswalk, locations = apply_location_resolution_decisions(
        profiles,
        anomalies,
        profile_decisions,
        location_pairs,
        location_decisions,
    )
    write_csv_atomic(crosswalk, args.crosswalk_output)
    write_csv_atomic(locations, args.location_output)

    included = crosswalk["final_profile_status"].eq("included")
    summary = {
        "input_profiles": len(profiles),
        "input_location_groups": int(profiles["physical_location_group"].nunique()),
        "profile_decisions_applied": len(profile_decisions),
        "excluded_profiles": int((~included).sum()),
        "included_profiles": int(included.sum()),
        "reviewed_group_pairs": len(location_decisions),
        "group_merges_applied": int(
            location_decisions["location_decision"].eq("merge_groups").sum()
        ),
        "final_physical_locations": len(locations),
        "final_locations_by_market": {
            str(key): int(value)
            for key, value in locations["mapped_location"]
            .value_counts().sort_index().items()
        },
        "profiles_without_final_location": int(
            crosswalk.loc[included, "final_physical_location_id"].isna().sum()
        ),
        "automatic_exclusions": 0,
        "automatic_merges": 0,
        "crosswalk_output": str(args.crosswalk_output),
        "location_output": str(args.location_output),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.summary.with_suffix(f"{args.summary.suffix}.tmp")
    temporary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(args.summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
