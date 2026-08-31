"""Validate clinic and rating input files before analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from medical_ratings.identifiers import build_clinic_key
from medical_ratings.validation import add_rating_reconciliation, missingness_summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("missingness_csv", type=Path)
    args = parser.parse_args()

    data = pd.read_csv(args.input_csv)
    data["clinic_key"] = data.apply(lambda row: build_clinic_key(row.to_dict()), axis=1)
    validated = add_rating_reconciliation(data)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    args.missingness_csv.parent.mkdir(parents=True, exist_ok=True)
    validated.to_csv(args.output_csv, index=False)
    missingness_summary(validated).to_csv(args.missingness_csv)


if __name__ == "__main__":
    main()
