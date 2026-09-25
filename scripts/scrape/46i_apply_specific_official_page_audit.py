"""Generate outputs from the frozen 39-profile human official-page decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.profile_eligibility_priority_audit import (
    apply_priority_singleton_audit,
)
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_context_arguments(parser)
    parser.add_argument("--priority-batch", type=Path, default=None)
    parser.add_argument("--singleton-audit", type=Path, default=None)
    parser.add_argument(
        "--decisions",
        type=Path,
        default=Path("config/profile_eligibility_specific_page_decisions_20260925.csv"),
    )
    parser.add_argument(
        "--verified-decisions",
        type=Path,
        default=Path("config/profile_eligibility_verified_decisions_20260924.csv"),
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "priority_batch": (
                "interim",
                "profile_eligibility_singleton_audit/specific_official_page_priority_batch.csv",
            ),
            "singleton_audit": (
                "interim",
                "profile_eligibility_singleton_audit/singleton_profile_audit.csv",
            ),
            "output_directory": (
                "interim",
                "profile_eligibility_priority_audit",
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
    inputs = [
        args.priority_batch,
        args.singleton_audit,
        args.decisions,
        args.verified_decisions,
    ]
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing audit inputs: " + ", ".join(missing))
    outputs = [
        args.output_directory / "specific_page_verified_additions.csv",
        args.output_directory / "profile_eligibility_verified_decisions_updated.csv",
        args.output_directory / "remaining_singleton_profile_audit.csv",
        args.output_directory / "specific_page_audit_summary.json",
    ]
    existing = [str(path) for path in outputs if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(existing) + ". Use --overwrite."
        )

    additions, combined, remainder, summary = apply_priority_singleton_audit(
        pd.read_csv(args.priority_batch, dtype=str, keep_default_na=False),
        pd.read_csv(args.decisions, dtype=str, keep_default_na=False),
        pd.read_csv(args.singleton_audit, dtype=str, keep_default_na=False),
        pd.read_csv(args.verified_decisions, dtype=str, keep_default_na=False),
    )
    _write_csv(additions, outputs[0])
    _write_csv(combined, outputs[1])
    _write_csv(remainder, outputs[2])
    summary["input_lineage"] = {
        "priority_batch": str(args.priority_batch),
        "singleton_audit": str(args.singleton_audit),
        "human_decisions": str(args.decisions),
        "verified_decisions_before": str(args.verified_decisions),
    }
    summary["decision_generation"] = (
        "manual_official_page_audit_input_not_generated_by_code"
    )
    _write_json(summary, outputs[3])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
