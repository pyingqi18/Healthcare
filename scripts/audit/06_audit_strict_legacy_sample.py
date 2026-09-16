"""Audit strict 009a and compatible two-mile sample differences."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.strict_legacy_sample_audit import (
    audit_strict_legacy_sample,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit strict and compatible 009a two-mile samples."
    )
    parser.add_argument("--base-panel", type=Path, required=True)
    parser.add_argument("--clinics", type=Path, required=True)
    parser.add_argument("--strict-panel", type=Path, required=True)
    parser.add_argument("--compatible-panel", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    base_panel = pd.read_csv(args.base_panel, low_memory=False)
    clinics = pd.read_csv(args.clinics, low_memory=False)
    strict_panel = pd.read_csv(args.strict_panel, low_memory=False)
    compatible_panel = pd.read_csv(args.compatible_panel, low_memory=False)

    detail, missing_panel, relation_summary, metadata = (
        audit_strict_legacy_sample(
            base_panel,
            clinics,
            strict_panel,
            compatible_panel,
        )
    )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    detail.to_csv(
        args.output_directory / "strict_vs_compatible_clinic_membership.csv",
        index=False,
    )
    missing_panel.to_csv(
        args.output_directory / "strict_pool_missing_from_panel.csv",
        index=False,
    )
    relation_summary.to_csv(
        args.output_directory / "strict_vs_compatible_pool_summary.csv",
        index=False,
    )
    (args.output_directory / "strict_legacy_sample_audit_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
