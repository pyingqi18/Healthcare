"""Tests for pagination-gated batch parsing of one rollout stage."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/scrape/15a_parse_business_listings_rollout_stage.py"
SPEC = importlib.util.spec_from_file_location("business_listings_stage_parse", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def result_log() -> pd.DataFrame:
    rows = []
    for market in [f"Market_{index:02d}" for index in range(10)]:
        page_count = 3 if market == "Market_09" else 2
        for page in range(1, page_count + 1):
            group = 1 if page < page_count else 2
            rows.append(
                {
                    "task_tag": f"rollout:{market}:g{group:02d}:p{page:02d}",
                    "stage": "standard_rollout",
                    "market": market,
                    "request_status": "completed",
                }
            )
    rows.append(
        {
            "task_tag": "rollout:Atlanta_GA_L:g01:p01",
            "stage": "large_market_validation",
            "market": "Atlanta_GA_L",
            "request_status": "completed",
        }
    )
    return pd.DataFrame(rows)


def group_audit() -> pd.DataFrame:
    rows = []
    for market in [f"Market_{index:02d}" for index in range(10)]:
        rows.extend(
            [
                {
                    "market": market,
                    "category_group": 1,
                    "saved_page_count": 2 if market == "Market_09" else 1,
                    "category_group_complete": True,
                },
                {
                    "market": market,
                    "category_group": 2,
                    "saved_page_count": 1,
                    "category_group_complete": True,
                },
            ]
        )
    rows.append(
        {
            "market": "Atlanta_GA_L",
            "category_group": 1,
            "saved_page_count": 1,
            "category_group_complete": True,
        }
    )
    return pd.DataFrame(rows)


def test_select_complete_stage_markets_uses_only_requested_stage() -> None:
    selected = MODULE.select_complete_stage_markets(
        result_log(),
        group_audit(),
        stage="standard_rollout",
    )
    assert len(selected) == 10
    assert "Atlanta_GA_L" not in set(selected["market"])
    assert int(selected["completed_pages"].sum()) == 21
    assert int(
        selected.loc[selected["market"].eq("Market_09"), "completed_pages"].iloc[0]
    ) == 3


def test_select_complete_stage_markets_rejects_incomplete_group() -> None:
    groups = group_audit()
    groups.loc[
        groups["market"].eq("Market_04") & groups["category_group"].eq(1),
        "category_group_complete",
    ] = False
    with pytest.raises(ValueError, match="incomplete for market: Market_04"):
        MODULE.select_complete_stage_markets(
            result_log(),
            groups,
            stage="standard_rollout",
        )


def test_select_complete_stage_markets_rejects_page_count_mismatch() -> None:
    log = result_log().loc[
        lambda frame: ~frame["task_tag"].eq("rollout:Market_09:g01:p02")
    ]
    with pytest.raises(ValueError, match="Completed page count differs"):
        MODULE.select_complete_stage_markets(
            log,
            group_audit(),
            stage="standard_rollout",
        )
