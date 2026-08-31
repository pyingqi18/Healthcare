"""Run the registered main fixed-effects specification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.models import PanelSpecification, fit_market_year_fe


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("panel_csv", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--include-log-votes", action="store_true")
    args = parser.parse_args()

    controls = ("log_votes_dynamic",) if args.include_log_votes else ()
    specification = PanelSpecification(
        name="main_market_year_fe",
        outcome="dynamic_rating",
        exposures=("log_entry_shock_inner_count", "log_density_inner_count"),
        controls=controls,
    )

    panel = pd.read_csv(args.panel_csv)
    result = fit_market_year_fe(panel, specification)

    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / "main_specification.json").write_text(
        json.dumps(specification.to_dict(), indent=2), encoding="utf-8"
    )
    (args.output_directory / "main_regression.txt").write_text(
        str(result.summary), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
