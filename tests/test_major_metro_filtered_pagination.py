"""Tests for ZIP-filtered major-metro offset-token pagination."""

import importlib.util
from argparse import Namespace
from pathlib import Path

import pandas as pd
import pytest
import yaml

from medical_ratings.business_listings_rollout import (
    audit_major_metro_filtered_page_log,
    build_major_metro_filtered_page_plan,
    build_rollout_first_page_plan,
)


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict[str, object]:
    value = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def source_and_counts() -> tuple[pd.DataFrame, pd.DataFrame]:
    config = load_yaml("config/scrape_plans.yaml")
    regions = load_yaml("config/regions.yaml")
    categories = pd.read_csv(ROOT / "config/business_listings_dental_categories.csv")
    source, _ = build_rollout_first_page_plan(config, regions, categories)
    totals = {
        ("LA_CA_L", 1): 11576,
        ("LA_CA_L", 2): 1773,
        ("NYC_NY_L", 1): 12619,
        ("NYC_NY_L", 2): 1587,
    }
    records = []
    for (market, group), total in totals.items():
        records.append(
            {
                "task_tag": (
                    "business_listings_major_metro_filter_count:"
                    f"{market}:g{group:02d}:p01"
                ),
                "request_status": "completed",
                "total_count": total,
                "item_count": 1,
            }
        )
    return source, pd.DataFrame.from_records(records)


def build_plan() -> tuple[pd.DataFrame, dict[str, object]]:
    source, counts = source_and_counts()
    return build_major_metro_filtered_page_plan(
        source,
        counts,
        load_yaml("config/scrape_plans.yaml"),
        load_yaml("config/regions.yaml"),
    )


def test_filtered_page_plan_uses_twenty_nine_token_requests() -> None:
    plan, summary = build_plan()
    assert len(plan) == 4
    pages = plan.set_index(["market", "category_group"])["planned_page_count"]
    assert pages.to_dict() == {
        ("LA_CA_L", 1): 12,
        ("LA_CA_L", 2): 2,
        ("NYC_NY_L", 1): 13,
        ("NYC_NY_L", 2): 2,
    }
    assert summary["audited_filtered_items"] == 27555
    assert summary["planned_page_requests"] == 29
    assert summary["estimated_total_cost_usd"] == pytest.approx(10.2678)
    assert plan["api_task_tag"].nunique() == 4


def test_filtered_page_state_requires_contiguous_token_chain() -> None:
    plan, _ = build_plan()
    group = plan.loc[plan["group_id"].eq("LA_CA_L:g01")].copy()
    group.loc[:, "audited_total_count"] = 2500
    group.loc[:, "planned_page_count"] = 3
    pages = pd.DataFrame(
        {
            "page_request_tag": ["la:g01:p01", "la:g01:p02"],
            "group_id": ["LA_CA_L:g01", "LA_CA_L:g01"],
            "page_number": [1, 2],
            "request_status": ["completed", "completed"],
            "item_count": [1000, 1000],
            "total_count": [2500, 2500],
            "offset_token_used": [None, "token-2"],
            "next_offset_token": ["token-2", "token-3"],
        }
    )
    state, summary = audit_major_metro_filtered_page_log(pages, group)
    assert summary["completed_page_requests"] == 2
    assert summary["remaining_planned_requests"] == 1
    assert state.iloc[0]["next_offset_token"] == "token-3"

    broken = pages.copy()
    broken.loc[1, "offset_token_used"] = "wrong-token"
    with pytest.raises(ValueError, match="chain is broken"):
        audit_major_metro_filtered_page_log(broken, group)


def test_filtered_page_runner_validation_reads_no_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source, counts = source_and_counts()
    source_path = tmp_path / "source.csv"
    count_path = tmp_path / "counts.csv"
    source.to_csv(source_path, index=False)
    counts.to_csv(count_path, index=False)
    script_path = ROOT / "scripts/scrape/25a_run_major_metro_zip_filtered_pages.py"
    spec = importlib.util.spec_from_file_location("filtered_page_runner", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "parse_arguments",
        lambda: Namespace(
            plan=source_path,
            count_log=count_path,
            plan_config=ROOT / "config/scrape_plans.yaml",
            regions=ROOT / "config/regions.yaml",
            settings=ROOT / "config/settings.yaml",
            results_directory=tmp_path / "raw",
            output_directory=tmp_path / "interim",
            confirm_submit=None,
        ),
    )
    assert module.main() == 0
    output = capsys.readouterr().out
    assert '"remaining_planned_requests": 29' in output
    assert '"remaining_estimated_cost_usd": 10.2678' in output
    assert '"credentials_read": false' in output
    assert '"api_requests_submitted": 0' in output
    assert "SUBMIT_29_PAID_MAJOR_METRO_ZIP_FILTERED_PAGE_REQUESTS" in output
