"""Build the local browser interface for profile eligibility review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from medical_ratings.profile_eligibility_review_app import (
    build_profile_eligibility_review_app,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a self-contained local HTML app for manual profile review."
    )
    add_run_context_arguments(parser)
    parser.add_argument("--rows", type=Path, default=None)
    parser.add_argument("--groups", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "rows": ("interim", "profile_eligibility_review/profile_eligibility_review_rows.csv"),
            "groups": ("interim", "profile_eligibility_review/profile_eligibility_review_groups.csv"),
            "output": ("interim", "profile_eligibility_review/profile_eligibility_review.html"),
            "summary": ("interim", "profile_eligibility_review/profile_eligibility_review_app_summary.json"),
        },
    )


def _write_text_atomic(value: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    missing = [str(path) for path in [args.rows, args.groups] if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing profile review inputs: " + ", ".join(missing))
    existing = [str(path) for path in [args.output, args.summary] if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(existing) + ". Use --overwrite."
        )
    html, summary = build_profile_eligibility_review_app(
        pd.read_csv(args.rows, dtype=str, keep_default_na=False, low_memory=False),
        pd.read_csv(args.groups, dtype=str, keep_default_na=False, low_memory=False),
    )
    _write_text_atomic(html, args.output)
    _write_text_atomic(
        json.dumps(summary, ensure_ascii=False, indent=2), args.summary
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
