"""Freeze the 15-market discovery benchmark and cancel residual search."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.discovery_benchmark_freeze import freeze_discovery_benchmark
from medical_ratings.scrape_run_context import (
    add_run_context_arguments,
    resolve_run_context_arguments,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the completed reference-status audit, cancel the conditional "
            "75-task residual manifest, and freeze the discovery benchmark."
        )
    )
    add_run_context_arguments(parser)
    parser.add_argument("--adjudication-summary", type=Path, default=None)
    parser.add_argument("--market-audit", type=Path, default=None)
    parser.add_argument("--source-union", type=Path, default=None)
    parser.add_argument("--residual-manifest", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return resolve_run_context_arguments(
        args,
        {
            "adjudication_summary": (
                "interim",
                "reference_status_audit_adjudication/"
                "reference_status_adjudication_summary.json",
            ),
            "market_audit": (
                "interim",
                "reference_status_audit_adjudication/"
                "reference_status_audit_by_market.csv",
            ),
            "source_union": (
                "interim",
                "reference_status_audit_adjudication/"
                "source_union_after_reference_status_audit.csv",
            ),
            "residual_manifest": (
                "interim",
                "post_adjudication_completion_plan/"
                "uniform_residual_keyword_manifest.csv",
            ),
            "output_directory": ("interim", "primary_discovery_benchmark_freeze"),
        },
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    outputs = {
        "union": args.output_directory / "frozen_active_reference_source_union.csv",
        "markets": args.output_directory / "frozen_discovery_benchmark_by_market.csv",
        "carry_forward": (
            args.output_directory / "validated_legacy_carry_forward_inventory.csv"
        ),
        "cancelled": (
            args.output_directory / "uniform_residual_keyword_manifest_cancelled.csv"
        ),
        "summary": args.output_directory / "discovery_benchmark_freeze_summary.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Output already exists: "
            + ", ".join(str(path) for path in existing)
            + ". Use --overwrite to replace it."
        )

    input_paths = {
        "adjudication_summary": args.adjudication_summary,
        "market_audit": args.market_audit,
        "source_union": args.source_union,
        "residual_manifest": args.residual_manifest,
    }
    missing = [str(path) for path in input_paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing freeze inputs: " + ", ".join(missing))

    adjudication_summary = json.loads(
        args.adjudication_summary.read_text(encoding="utf-8")
    )
    active, markets, carry_forward, cancelled, summary = freeze_discovery_benchmark(
        adjudication_summary,
        pd.read_csv(args.market_audit, low_memory=False),
        pd.read_csv(args.source_union, low_memory=False),
        pd.read_csv(args.residual_manifest, low_memory=False),
    )
    summary["input_sha256"] = {
        label: _sha256(path) for label, path in input_paths.items()
    }
    _write_csv(active, outputs["union"])
    _write_csv(markets, outputs["markets"])
    _write_csv(carry_forward, outputs["carry_forward"])
    _write_csv(cancelled, outputs["cancelled"])
    _write_json(summary, outputs["summary"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(markets.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
