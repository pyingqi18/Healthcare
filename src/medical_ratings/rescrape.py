"""Build deterministic manifests for corrected-location rescrapes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import Any

import pandas as pd


LEGACY_KEYWORD_GROUPS: dict[str, tuple[str, ...]] = {
    "general": (
        "dental clinic",
        "family dentist",
        "dentist",
        "general dentistry",
        "cosmetic dentist",
    ),
    "specialist": (
        "orthodontist",
        "pediatric dentist",
        "periodontist",
        "prosthodontist",
    ),
    "surgery": (
        "oral surgeon",
        "dental implants",
        "emergency dentist",
    ),
}

SEARCH_API_TYPES = ("local_finder", "maps")
KNOWN_INVALID_LOCATION_CODES = {1026588, 1027001}


def _keyword_combinations(
    keywords: Sequence[str],
) -> list[tuple[str, ...]]:
    """Return every non-empty combination in deterministic order."""

    return [
        combination
        for size in range(1, len(keywords) + 1)
        for combination in combinations(keywords, size)
    ]


def build_location_rescrape_manifest(
    regions_config: Mapping[str, Any],
    *,
    target_regions: Sequence[str],
    language_code: str = "en",
    depth: int = 100,
) -> pd.DataFrame:
    """Plan search tasks without submitting them to DataForSEO."""

    regions = regions_config.get("regions")
    if not isinstance(regions, Mapping):
        raise KeyError("regions_config must contain a 'regions' mapping")

    parsed_depth = int(depth)
    if parsed_depth < 1:
        raise ValueError("depth must be positive")

    rows: list[dict[str, Any]] = []

    for region_key in target_regions:
        region = regions.get(region_key)
        if not isinstance(region, Mapping):
            raise KeyError(f"Unknown target region: {region_key}")

        if region.get("location_code") is None:
            raise KeyError(f"Missing location_code for region: {region_key}")

        location_code = int(region["location_code"])
        if location_code in KNOWN_INVALID_LOCATION_CODES:
            raise ValueError(
                f"Known invalid location_code for {region_key}: "
                f"{location_code}"
            )

        for category, keywords in LEGACY_KEYWORD_GROUPS.items():
            keyword_sets = _keyword_combinations(keywords)

            for combination_index, keyword_set in enumerate(
                keyword_sets,
                start=1,
            ):
                query = "+".join(keyword_set)

                for api_type in SEARCH_API_TYPES:
                    task_tag = (
                        f"{region_key}:{api_type}:"
                        f"{category}:{combination_index:02d}"
                    )
                    rows.append(
                        {
                            "task_tag": task_tag,
                            "region_key": region_key,
                            "location_code": location_code,
                            "api_type": api_type,
                            "keyword_category": category,
                            "combination_size": len(keyword_set),
                            "query": query,
                            "language_code": language_code,
                            "depth": parsed_depth,
                        }
                    )

    manifest = pd.DataFrame.from_records(rows)
    if not manifest.empty and not manifest["task_tag"].is_unique:
        raise ValueError("Generated task_tag values are not unique")

    return manifest
