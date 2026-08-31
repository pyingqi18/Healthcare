"""Build a cumulative clinic-year panel from clinic and review files."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from medical_ratings.panel import aggregate_reviews, build_cumulative_panel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("clinics_csv", type=Path)
    parser.add_argument("reviews_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--end-year", type=int, default=2025)
    args = parser.parse_args()

    clinics = pd.read_csv(args.clinics_csv)
    reviews = pd.read_csv(args.reviews_csv)
    yearly = aggregate_reviews(reviews)
    panel = build_cumulative_panel(clinics, yearly, end_year=args.end_year)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(args.output_csv, index=False)


if __name__ == "__main__":
    main()
