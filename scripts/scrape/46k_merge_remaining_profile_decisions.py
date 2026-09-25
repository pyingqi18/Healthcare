"""Merge one reviewed profile-eligibility batch into the stage 46 checkpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.profile_eligibility_completion import (
    merge_remaining_decision_batch,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--allow-corrections", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def _guard(paths: list[Path], overwrite: bool) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Output already exists: " + ", ".join(existing) + ". Use --overwrite."
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
    missing = [str(path) for path in [args.checkpoint, args.batch] if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing decision inputs: " + ", ".join(missing))
    _guard([args.output, args.summary_output], args.overwrite)
    merged, summary = merge_remaining_decision_batch(
        _read(args.checkpoint),
        _read(args.batch),
        allow_corrections=args.allow_corrections,
    )
    summary["input_lineage"] = {
        "checkpoint": str(args.checkpoint),
        "batch": str(args.batch),
    }
    _write_csv(merged, args.output)
    _write_json(summary, args.summary_output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
