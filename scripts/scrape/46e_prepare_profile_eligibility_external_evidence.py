"""Prepare the unresolved external-evidence profiles as a compact audit queue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.profile_eligibility_external_evidence import (
    prepare_external_evidence_audit,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build unit, profile, and domain queues for unresolved external profile "
            "evidence without making eligibility decisions or requesting an API."
        )
    )
    add_run_context_arguments(parser)
    parser.add_argument("--review-rows", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "review_rows": (
                "interim",
                "profile_eligibility_review/profile_eligibility_review_rows.csv",
            ),
            "output_directory": (
                "interim",
                "profile_eligibility_external_evidence_audit",
            ),
        },
    )


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    if not args.review_rows.exists():
        raise FileNotFoundError(f"Missing profile review rows: {args.review_rows}")
    outputs = [
        args.output_directory / "external_evidence_audit_units.csv",
        args.output_directory / "external_evidence_profiles.csv",
        args.output_directory / "external_evidence_domains.csv",
        args.output_directory / "external_evidence_audit_summary.json",
    ]
    existing = [str(path) for path in outputs if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(existing) + ". Use --overwrite."
        )
    units, profiles, domains, summary = prepare_external_evidence_audit(
        pd.read_csv(args.review_rows, dtype=str, keep_default_na=False, low_memory=False)
    )
    _write_csv(units, outputs[0])
    _write_csv(profiles, outputs[1])
    _write_csv(domains, outputs[2])
    _write_json(summary, outputs[3])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
