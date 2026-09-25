"""Freeze v8 evidence and append the exact shared-domain profile decisions."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from medical_ratings.profile_eligibility_audit_freeze import (
    DECISION_COLUMN_ORDER,
    merge_verified_decisions,
    sha256_file,
    validate_shared_domain_decisions,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-rows", type=Path, required=True)
    parser.add_argument("--review-groups", type=Path, required=True)
    parser.add_argument("--review-summary", type=Path, required=True)
    parser.add_argument("--external-profiles", type=Path, required=True)
    parser.add_argument("--external-units", type=Path, required=True)
    parser.add_argument("--external-domains", type=Path, required=True)
    parser.add_argument("--external-summary", type=Path, required=True)
    parser.add_argument(
        "--shared-domain-decisions",
        type=Path,
        default=Path("config/profile_eligibility_shared_domain_decisions_20260924.csv"),
    )
    parser.add_argument(
        "--verified-decisions",
        type=Path,
        default=Path("config/profile_eligibility_verified_decisions_20260924.csv"),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("archive/profile_eligibility_review/20260924_v8"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _write_json(payload: dict[str, Any], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    args = parse_arguments()
    inputs = {
        "profile_eligibility_review_rows_v8.csv": args.review_rows,
        "profile_eligibility_review_groups_v8.csv": args.review_groups,
        "profile_eligibility_review_prepare_summary_v8.json": args.review_summary,
        "external_evidence_profiles.csv": args.external_profiles,
        "external_evidence_audit_units.csv": args.external_units,
        "external_evidence_domains.csv": args.external_domains,
        "external_evidence_audit_summary.json": args.external_summary,
        "verified_decisions_at_execution.csv": args.verified_decisions,
        "shared_domain_profile_decisions.csv": args.shared_domain_decisions,
    }
    missing = [str(path) for path in inputs.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing freeze inputs: " + ", ".join(missing))
    if args.output_directory.exists() and not args.overwrite:
        raise FileExistsError(
            f"Freeze directory already exists: {args.output_directory}. Use --overwrite."
        )
    if args.output_directory.exists():
        shutil.rmtree(args.output_directory)
    source_dir = args.output_directory / "source_inputs"
    source_dir.mkdir(parents=True)

    audited, audit_summary = validate_shared_domain_decisions(
        pd.read_csv(args.external_profiles, dtype=str, keep_default_na=False),
        pd.read_csv(args.shared_domain_decisions, dtype=str, keep_default_na=False),
    )
    existing = pd.read_csv(args.verified_decisions, dtype=str, keep_default_na=False)
    addition_keys = set(audited["profile_key"])
    overlap = set(existing["profile_key"]) & addition_keys
    if not overlap:
        earlier_verified_count = len(existing)
        combined = merge_verified_decisions(existing, audited)
    elif overlap == addition_keys:
        expected_additions = audited[DECISION_COLUMN_ORDER].sort_values(
            "profile_key", ignore_index=True
        )
        saved_additions = existing.loc[
            existing["profile_key"].isin(addition_keys), DECISION_COLUMN_ORDER
        ].sort_values("profile_key", ignore_index=True)
        if not expected_additions.equals(saved_additions):
            raise ValueError(
                "Existing verified decisions disagree with the shared-domain audit"
            )
        earlier_verified_count = len(existing) - len(audited)
        combined = existing[DECISION_COLUMN_ORDER].copy()
    else:
        raise ValueError(
            "Verified decisions contain only part of the shared-domain audit; "
            "refuse a mixed partial state"
        )
    if earlier_verified_count != 163:
        raise ValueError(
            "Expected 163 decisions before the shared-domain audit; received "
            f"{earlier_verified_count}"
        )
    if len(combined) != 212:
        raise ValueError(f"Expected 212 combined verified decisions; received {len(combined)}")

    copied: dict[str, Path] = {}
    for frozen_name, source_path in inputs.items():
        destination = source_dir / frozen_name
        shutil.copy2(source_path, destination)
        copied[f"source_inputs/{frozen_name}"] = destination
    audit_path = args.output_directory / "shared_domain_profile_audit.csv"
    audited.to_csv(audit_path, index=False)
    copied[audit_path.name] = audit_path
    combined_path = args.output_directory / "verified_decisions_after_shared_domain_audit.csv"
    combined.to_csv(combined_path, index=False)
    copied[combined_path.name] = combined_path

    archive_path = args.output_directory / "profile_eligibility_review_freeze_20260924_v8.zip"
    audit_summary.update(
        {
            "frozen_review_version": "20260924_v8",
            "earlier_verified_decisions": earlier_verified_count,
            "verified_decisions_after_shared_domain_audit": len(combined),
            "remaining_review_profiles": 450 - len(combined),
            "original_files_retained": True,
            "original_zip_required_for_future_review": False,
            "review_files": sorted(copied),
            "freeze_archive": str(archive_path),
        }
    )
    summary_path = args.output_directory / "shared_domain_profile_audit_summary.json"
    _write_json(audit_summary, summary_path)
    copied[summary_path.name] = summary_path

    manifest_rows = [
        {
            "relative_path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for relative, path in sorted(copied.items())
    ]
    manifest = pd.DataFrame(manifest_rows)
    manifest_path = args.output_directory / "MANIFEST.sha256.csv"
    manifest.to_csv(manifest_path, index=False)
    copied[manifest_path.name] = manifest_path

    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for relative, path in sorted(copied.items()):
            archive.write(path, arcname=relative)
    archive_metadata = {
        **audit_summary,
        "freeze_archive_sha256": sha256_file(archive_path),
        "archive_manifest_sha256": sha256_file(manifest_path),
    }
    archive_metadata_path = args.output_directory / "freeze_archive_metadata.json"
    _write_json(archive_metadata, archive_metadata_path)
    print(json.dumps(archive_metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
