from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.maps_specialist_plan import validate_specialist_manifest
from medical_ratings.maps_supplement import keyword_profile_summary


MARKETS = {f"Market_{index}" for index in range(15)}
KEYWORDS = {
    "orthodontist",
    "pediatric dentist",
    "periodontist",
    "prosthodontist",
    "oral surgeon",
}


def manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_tag": f"tag:{market}:{keyword}",
                "plan_type": "market_specialist_discovery",
                "market": market,
                "query": keyword,
                "location_code": 1000,
                "language_code": "en",
                "depth": 100,
                "priority": 1,
                "included_in_main_discovery_pipeline": True,
            }
            for market in sorted(MARKETS)
            for keyword in sorted(KEYWORDS)
        ]
    )


def test_accepts_exact_uniform_seventy_five_task_manifest() -> None:
    validate_specialist_manifest(
        manifest(), expected_markets=MARKETS, expected_keywords=KEYWORDS
    )


def test_rejects_one_market_using_a_different_keyword_set() -> None:
    frame = manifest()
    frame.loc[0, "query"] = "emergency dentist"
    with pytest.raises(ValueError, match="keywords differ"):
        validate_specialist_manifest(
            frame, expected_markets=MARKETS, expected_keywords=KEYWORDS
        )


def test_keyword_profile_summary_counts_shared_and_exclusive_profiles() -> None:
    candidates = pd.DataFrame(
        {
            "requested_location": ["Market_A", "Market_A", "Market_A"],
            "profile_key": ["a", "b", "c"],
            "observed_queries": [
                "orthodontist",
                "oral surgeon|orthodontist",
                "oral surgeon",
            ],
        }
    )
    summary = keyword_profile_summary(candidates).set_index("query")
    assert summary.loc["orthodontist", "profiles_observed"] == 2
    assert summary.loc["orthodontist", "profiles_exclusive_to_query"] == 1
    assert summary.loc["oral surgeon", "profiles_observed"] == 2


def test_rejects_manifest_rows_outside_main_discovery() -> None:
    frame = manifest()
    frame.loc[0, "included_in_main_discovery_pipeline"] = False
    with pytest.raises(ValueError, match="outside main discovery"):
        validate_specialist_manifest(
            frame, expected_markets=MARKETS, expected_keywords=KEYWORDS
        )
