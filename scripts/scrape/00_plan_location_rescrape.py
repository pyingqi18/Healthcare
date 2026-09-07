"""Create a dry-run manifest for corrected-location clinic searches."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from medical_ratings.rescrape import build_location_rescrape_manifest


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan corrected-location searches without submitting API tasks."
    )
    parser.add_argument(
        "--regions",
        type=Path,
        default=Path("config/regions.yaml"),
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("config/settings.yaml"),
    )
    parser.add_argument(
        "--target-regions",
        nargs="+",
        default=["Malone_NY_S", "Syracuse_NY_M"],
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
    )
    return parser.parse_args()


def read_yaml(path: Path) -> dict[str, object]:
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise TypeError(f"Expected a YAML mapping: {path}")
    return content


def main() -> None:
    args = parse_arguments()
    regions_config = read_yaml(args.regions)
    settings = read_yaml(args.settings)

    dataforseo = settings.get("dataforseo")
    if not isinstance(dataforseo, dict):
        raise KeyError("settings.yaml is missing dataforseo")

    manifest = build_location_rescrape_manifest(
        regions_config,
        target_regions=args.target_regions,
        language_code=str(dataforseo.get("language_code", "en")),
        depth=int(dataforseo.get("depth", 100)),
    )

    manifest_path = args.output_directory / "clinic_search_manifest.csv"
    summary_path = args.output_directory / "clinic_search_manifest_summary.json"

    existing_outputs = [
        path
        for path in (manifest_path, summary_path)
        if path.exists()
    ]
    if existing_outputs and not args.overwrite:
        paths = ", ".join(str(path) for path in existing_outputs)
        raise FileExistsError(
            f"Output already exists: {paths}. Use --overwrite to replace it."
        )

    args.output_directory.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(manifest_path, index=False)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dry_run_only": True,
        "api_tasks_submitted": 0,
        "target_regions": list(args.target_regions),
        "total_planned_tasks": len(manifest),
        "unique_task_tags": int(manifest["task_tag"].nunique()),
        "tasks_by_region": {
            str(key): int(value)
            for key, value in manifest["region_key"].value_counts().items()
        },
        "tasks_by_api": {
            str(key): int(value)
            for key, value in manifest["api_type"].value_counts().items()
        },
        "tasks_by_keyword_category": {
            str(key): int(value)
            for key, value in manifest[
                "keyword_category"
            ].value_counts().items()
        },
        "location_codes": sorted(
            int(value) for value in manifest["location_code"].unique()
        ),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
