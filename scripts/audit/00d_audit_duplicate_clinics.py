"""Audit duplicate clinic identity keys."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from medical_ratings.identifiers import build_clinic_key


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit duplicate clinic identity keys."
    )
    parser.add_argument(
        "--clinics",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    clinics = pd.read_csv(
        args.clinics,
        low_memory=False,
    )

    original_columns = clinics.columns.tolist()

    clinics["clinic_key"] = clinics.apply(
        lambda row: build_clinic_key(row.to_dict()),
        axis=1,
    )

    duplicate_mask = clinics["clinic_key"].duplicated(
        keep=False,
    )

    duplicates = clinics.loc[
        duplicate_mask
    ].copy()

    duplicates.insert(
        0,
        "source_row",
        duplicates.index,
    )

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    duplicates.to_csv(
        args.output_directory
        / "duplicate_clinic_rows.csv",
        index=False,
    )

    group_records = []
    differing_column_counter: Counter[str] = Counter()
    exact_duplicate_groups = 0
    nonidentical_duplicate_groups = 0
    google_key_groups = 0
    fallback_key_groups = 0

    for clinic_key, group in clinics.loc[
        duplicate_mask
    ].groupby("clinic_key"):
        differing_columns = []

        for column in original_columns:
            comparable = (
                group[column]
                .astype("string")
                .fillna("<MISSING>")
            )

            if comparable.nunique(dropna=False) > 1:
                differing_columns.append(column)
                differing_column_counter[column] += 1

        exact_duplicate = len(differing_columns) == 0

        if exact_duplicate:
            exact_duplicate_groups += 1
        else:
            nonidentical_duplicate_groups += 1

        if str(clinic_key).startswith("google:"):
            key_type = "google"
            google_key_groups += 1
        else:
            key_type = "fallback"
            fallback_key_groups += 1

        group_records.append(
            {
                "clinic_key": clinic_key,
                "row_count": len(group),
                "key_type": key_type,
                "exact_duplicate": exact_duplicate,
                "differing_column_count": len(
                    differing_columns
                ),
                "differing_columns": "|".join(
                    differing_columns
                ),
            }
        )

    group_summary = pd.DataFrame(group_records)

    group_summary.to_csv(
        args.output_directory
        / "duplicate_clinic_groups.csv",
        index=False,
    )

    summary = {
        "total_clinic_rows": len(clinics),
        "duplicate_clinic_rows": len(duplicates),
        "duplicate_clinic_key_groups": len(
            group_summary
        ),
        "exact_duplicate_groups": exact_duplicate_groups,
        "nonidentical_duplicate_groups": (
            nonidentical_duplicate_groups
        ),
        "google_key_groups": google_key_groups,
        "fallback_key_groups": fallback_key_groups,
        "differing_column_frequency": dict(
            differing_column_counter.most_common()
        ),
    }

    summary_path = (
        args.output_directory
        / "duplicate_clinic_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()