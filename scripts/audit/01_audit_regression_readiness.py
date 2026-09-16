"""Audit whether a clinic-year panel is ready for fixed-effects regression."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.regression_readiness import audit_regression_readiness


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit regression inputs without fitting a model."
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--outcome", default="dynamic_rating")
    parser.add_argument(
        "--exposure",
        action="append",
        dest="exposures",
        help=(
            "Required exposure column. Repeat for multiple exposures. "
            "Defaults to the current main-regression columns."
        ),
    )
    parser.add_argument("--market-column")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    exposures = args.exposures or [
        "log_entry_shock_inner_count",
        "log_density_inner_count",
    ]

    panel = pd.read_csv(args.panel, low_memory=False)
    summary = audit_regression_readiness(
        panel,
        outcome=args.outcome,
        exposures=exposures,
        market_column=args.market_column,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
