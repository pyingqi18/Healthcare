"""Freeze the untouched 583 to 570 to 450 profile-review lineage."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from medical_ratings.profile_eligibility_original_freeze import (
    validate_original_review_lineage,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-pending", type=Path, required=True)
    parser.add_argument("--initial-summary", type=Path, required=True)
    parser.add_argument("--corrected-pending", type=Path, required=True)
    parser.add_argument("--corrected-summary", type=Path, required=True)
    parser.add_argument("--canonical-rows", type=Path, required=True)
    parser.add_argument("--canonical-groups", type=Path, required=True)
    parser.add_argument("--canonical-summary", type=Path, required=True)
    parser.add_argument("--triage", type=Path, required=True)
    parser.add_argument("--triage-groups", type=Path, required=True)
    parser.add_argument("--triage-summary", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "archive/profile_eligibility_review/original_manual_review_20260924"
        ),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_arguments()
    sources = {
        "00_initial_46a_pending_583_blank.csv": args.initial_pending,
        "00_initial_46a_summary.json": args.initial_summary,
        "01_corrected_46a_pending_570_blank.csv": args.corrected_pending,
        "01_corrected_46a_summary.json": args.corrected_summary,
        "02_canonical_manual_review_rows_450_blank.csv": args.canonical_rows,
        "03_canonical_manual_review_groups_410_blank.csv": args.canonical_groups,
        "03_canonical_manual_review_summary.json": args.canonical_summary,
        "04_profile_eligibility_triage_450.csv": args.triage,
        "05_profile_eligibility_category_groups_147.csv": args.triage_groups,
        "05_profile_eligibility_triage_summary.json": args.triage_summary,
        "06_unified_cross_source_profile_inventory_29984.csv": args.inventory,
    }
    missing = [str(path) for path in sources.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing original-review inputs: " + ", ".join(missing))
    if args.output_directory.exists() and not args.overwrite:
        raise FileExistsError(
            f"Freeze directory already exists: {args.output_directory}. Use --overwrite."
        )
    if args.output_directory.exists():
        shutil.rmtree(args.output_directory)
    data_directory = args.output_directory / "data"
    data_directory.mkdir(parents=True)

    summary = validate_original_review_lineage(
        pd.read_csv(args.initial_pending, dtype=str, keep_default_na=False),
        pd.read_csv(args.corrected_pending, dtype=str, keep_default_na=False),
        pd.read_csv(args.canonical_rows, dtype=str, keep_default_na=False),
        pd.read_csv(args.canonical_groups, dtype=str, keep_default_na=False),
        pd.read_csv(args.triage, dtype=str, keep_default_na=False),
        pd.read_csv(args.inventory, dtype=str, keep_default_na=False, low_memory=False),
    )
    copied: dict[str, Path] = {}
    for name, source in sources.items():
        destination = data_directory / name
        shutil.copy2(source, destination)
        copied[f"data/{name}"] = destination

    note = """# Original profile-eligibility review baseline\n\n+The canonical untouched human-review file is:\n+\n+`data/02_canonical_manual_review_rows_450_blank.csv`\n+\n+It contains 450 unique profiles and zero manual decisions. Its matching executable\n+block file is `data/03_canonical_manual_review_groups_410_blank.csv`.\n+\n+The 583-row and 570-row files are retained only to explain the upstream lineage.\n+The 583-row queue preceded reuse of 13 prior decisions. The 570-row queue preceded\n+120 unanimous frozen category exclusions. Neither is the final human-review cohort.\n+\n+Files called v8 or v9 are later progress checkpoints with 163 or 212 decisions and\n+must not be described as the original review baseline.\n+"""
    note_path = args.output_directory / "REVIEW_NOTE.md"
    note_path.write_text(note, encoding="utf-8")
    copied[note_path.name] = note_path
    summary_path = args.output_directory / "original_review_freeze_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    copied[summary_path.name] = summary_path

    manifest = pd.DataFrame.from_records(
        [
            {
                "relative_path": relative,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for relative, path in sorted(copied.items())
        ]
    )
    manifest_path = args.output_directory / "MANIFEST.sha256.csv"
    manifest.to_csv(manifest_path, index=False)
    copied[manifest_path.name] = manifest_path
    archive_path = args.output_directory / "original_profile_review_450_freeze.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for relative, path in sorted(copied.items()):
            archive.write(path, arcname=relative)
    metadata = {
        **summary,
        "freeze_archive": str(archive_path),
        "freeze_archive_sha256": _sha256(archive_path),
        "archive_manifest_sha256": _sha256(manifest_path),
    }
    (args.output_directory / "freeze_archive_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
