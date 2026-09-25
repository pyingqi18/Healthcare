"""Prepare the v9 unresolved singleton audit and its specific-page first batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.profile_eligibility_singleton_audit import (
    prepare_singleton_profile_audit,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_context_arguments(parser)
    parser.add_argument("--review-rows", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--expected-input-rows", type=int, default=450)
    parser.add_argument("--expected-decided-profiles", type=int, default=212)
    parser.add_argument("--expected-pending-profiles", type=int, default=238)
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
                "profile_eligibility_singleton_audit",
            ),
        },
    )


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    if not args.review_rows.exists():
        raise FileNotFoundError(f"Missing profile review rows: {args.review_rows}")
    outputs = [
        args.output_directory / "singleton_profile_audit.csv",
        args.output_directory / "specific_official_page_priority_batch.csv",
        args.output_directory / "singleton_profile_audit_summary.json",
    ]
    existing = [str(path) for path in outputs if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(existing) + ". Use --overwrite."
        )

    rows = pd.read_csv(
        args.review_rows, dtype=str, keep_default_na=False, low_memory=False
    )
    audit, priority_batch, summary = prepare_singleton_profile_audit(rows)
    observed = (
        len(rows),
        summary["already_decided_profiles"],
        summary["remaining_singleton_profiles"],
    )
    expected = (
        args.expected_input_rows,
        args.expected_decided_profiles,
        args.expected_pending_profiles,
    )
    if observed != expected:
        raise ValueError(
            "Profile review state differs from the frozen v9 checkpoint: "
            f"observed={observed}, expected={expected}"
        )

    _write_csv(audit, outputs[0])
    _write_csv(priority_batch, outputs[1])
    _write_json(summary, outputs[2])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
