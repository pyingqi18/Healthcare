"""Tests for staged Business Listings rollout planning and coverage checks."""

import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import pandas as pd
import pytest
import yaml

from medical_ratings.business_listings_rollout import (
    audit_major_metro_first_pages,
    build_major_metro_filtered_count_plan,
    audit_rollout_reference_envelope,
    build_rollout_continuation_plan,
    build_rollout_first_page_plan,
    select_major_metro_probe,
    select_next_paid_rollout_stage,
    validate_large_market_validation_summary,
    validate_rollout_first_page_plan,
)


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict[str, object]:
    value = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def inputs():
    return (
        load_yaml("config/scrape_plans.yaml"),
        load_yaml("config/regions.yaml"),
        pd.read_csv(ROOT / "config/business_listings_dental_categories.csv"),
    )


def test_rollout_plans_remaining_thirteen_markets_in_stages() -> None:
    config, regions, categories = inputs()
    plan, summary = build_rollout_first_page_plan(config, regions, categories)
    assert plan["market"].nunique() == 13
    assert len(plan) == 26
    assert plan.groupby("market")["category_count"].sum().eq(13).all()
    assert summary["requests_by_stage"] == {
        "large_market_validation": 2,
        "major_metro_review": 4,
        "standard_rollout": 20,
    }
    assert summary["next_paid_stage"] == {"market": "Atlanta_GA_L", "request_count": 2}
    assert plan["execution_enabled"].eq(False).all()


def test_rollout_rejects_execution_enabled_config() -> None:
    config, regions, categories = inputs()
    config["business_listings_rollout"]["execution_enabled"] = True
    with pytest.raises(ValueError, match="execution_enabled"):
        build_rollout_first_page_plan(config, regions, categories)


def test_only_atlanta_validation_can_be_selected_for_paid_stage() -> None:
    config, regions, categories = inputs()
    plan, _ = build_rollout_first_page_plan(config, regions, categories)
    validated = validate_rollout_first_page_plan(plan)
    assert len(validated) == 26
    selected = select_next_paid_rollout_stage(plan, "large_market_validation")
    assert len(selected) == 2
    assert set(selected["market"]) == {"Atlanta_GA_L"}
    with pytest.raises(ValueError, match="requires an approved"):
        select_next_paid_rollout_stage(plan, "standard_rollout")


def atlanta_validation_summary() -> dict[str, object]:
    return {
        "analysis_status": "rollout_market_comparison_before_manual_location_resolution",
        "market": "Atlanta_GA_L",
        "completed_paid_requests": 5,
        "reference_recall": {
            "reference_count": 397,
            "overall_recall": 370 / 397,
            "decision": "maps_supplement_required",
        },
        "legacy_reference_universe": {
            "eligible_target_zip_units": 397,
            "recall_denominator": "eligible_target_zip_units_only",
        },
    }


def test_corrected_atlanta_summary_approves_ten_market_standard_rollout() -> None:
    evidence = validate_large_market_validation_summary(
        atlanta_validation_summary()
    )
    assert evidence["reference_count"] == 397
    config, regions, categories = inputs()
    plan, _ = build_rollout_first_page_plan(config, regions, categories)
    selected = select_next_paid_rollout_stage(
        plan,
        "standard_rollout",
        standard_rollout_approved=True,
    )
    assert len(selected) == 20
    assert selected["market"].nunique() == 10
    assert {"NYC_NY_L", "LA_CA_L", "Atlanta_GA_L"}.isdisjoint(
        set(selected["market"])
    )


def major_metro_coverage() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "clinic_key": ["nyc-1", "nyc-2", "la-1"],
            "search_location": ["NYC_NY_L", "NYC_NY_L", "LA_CA_L"],
            "distance_from_hub_km": [10.0, 35.8, 62.6],
            "planned_radius_km": [45.0, 45.0, 75.0],
            "inside_planned_radius": [True, True, True],
        }
    )


def test_major_metro_probe_selects_four_requests_after_reference_check() -> None:
    config, regions, categories = inputs()
    plan, _ = build_rollout_first_page_plan(config, regions, categories)
    selected, evidence = select_major_metro_probe(plan, major_metro_coverage())
    assert len(selected) == 4
    assert set(selected["market"]) == {"NYC_NY_L", "LA_CA_L"}
    assert evidence["NYC_NY_L"]["zip_valid_reference_clinics"] == 2
    assert evidence["LA_CA_L"]["probe_radius_km"] == 75.0


def test_major_metro_probe_rejects_reference_outside_radius() -> None:
    config, regions, categories = inputs()
    plan, _ = build_rollout_first_page_plan(config, regions, categories)
    coverage = major_metro_coverage()
    coverage.loc[coverage["clinic_key"].eq("la-1"), "inside_planned_radius"] = False
    with pytest.raises(ValueError, match="outside the probe radius"):
        select_major_metro_probe(plan, coverage)


def test_major_metro_validation_uses_separate_confirmation_and_no_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config, regions, categories = inputs()
    plan, _ = build_rollout_first_page_plan(config, regions, categories)
    plan_path = tmp_path / "plan.csv"
    plan.to_csv(plan_path, index=False)
    coverage_path = tmp_path / "coverage.csv"
    major_metro_coverage().to_csv(coverage_path, index=False)
    script_path = ROOT / "scripts/scrape/11a_run_business_listings_rollout_stage.py"
    spec = importlib.util.spec_from_file_location("major_metro_runner", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "parse_arguments",
        lambda: Namespace(
            stage="major_metro_review",
            plan=plan_path,
            settings=ROOT / "config/settings.yaml",
            results_directory=tmp_path / "results",
            large_market_summary=tmp_path / "unused.json",
            reference_coverage=coverage_path,
            confirm_submit=None,
        ),
    )
    assert module.main() == 0
    output = capsys.readouterr().out
    assert '"stage_requests": 4' in output
    assert '"credentials_read": false' in output
    assert '"api_requests_submitted": 0' in output
    assert "SUBMIT_4_PAID_MAJOR_METRO_BUSINESS_LISTINGS_REQUESTS" in output


def test_major_metro_first_page_audit_reports_target_zip_yield_and_cost() -> None:
    observations = pd.DataFrame(
        {
            "task_tag": [
                "business_listings_rollout:NYC_NY_L:g01:p01",
                "business_listings_rollout:NYC_NY_L:g01:p01",
                "business_listings_rollout:NYC_NY_L:g02:p01",
                "business_listings_rollout:NYC_NY_L:g02:p01",
                "business_listings_rollout:LA_CA_L:g01:p01",
                "business_listings_rollout:LA_CA_L:g01:p01",
                "business_listings_rollout:LA_CA_L:g02:p01",
                "business_listings_rollout:LA_CA_L:g02:p01",
            ],
            "requested_location": ["NYC_NY_L"] * 4 + ["LA_CA_L"] * 4,
            "cid": [str(value) for value in range(8)],
            "place_id": [pd.NA] * 8,
            "zip": ["10001", "07030", "11201", pd.NA, "90001", "92801", "91601", pd.NA],
        }
    )
    groups = pd.DataFrame(
        {
            "market": ["NYC_NY_L", "NYC_NY_L", "LA_CA_L", "LA_CA_L"],
            "category_group": [1, 2, 1, 2],
            "reported_total_count": [20002, 2, 22002, 2],
            "saved_items_across_pages": [2, 2, 2, 2],
            "category_group_complete": [False, True, False, True],
        }
    )
    annotated, scope, summary = audit_major_metro_first_pages(
        observations,
        groups,
        load_yaml("config/regions.yaml"),
        request_cost_usd=0.012,
        item_cost_usd=0.00036,
    )
    assert len(annotated) == 8
    assert int(annotated["inside_target_zip"].sum()) == 4
    assert summary["groups_over_numeric_offset_guidance"] == 2
    assert summary["automatic_continuation_requests_submitted"] == 0
    large = scope.loc[scope["reported_total_count"].gt(10000)]
    assert large["recommended_next_action"].eq(
        "review_filter_or_partition_before_continuation"
    ).all()


def test_major_metro_filtered_count_plan_uses_exact_region_zip_regex() -> None:
    config, regions, categories = inputs()
    source_plan, _ = build_rollout_first_page_plan(config, regions, categories)
    plan, summary = build_major_metro_filtered_count_plan(
        source_plan, config, regions
    )
    assert len(plan) == 4
    assert plan["limit"].eq(1).all()
    assert plan["task_tag"].str.startswith(
        "business_listings_major_metro_filter_count:"
    ).all()
    assert plan["filters_json"].str.contains("address_info.zip", regex=False).all()
    assert summary["estimated_total_cost_usd"] == pytest.approx(0.04944)
    assert summary["automatic_continuation_requests_submitted"] == 0


def test_standard_rollout_validation_submits_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config, regions, categories = inputs()
    plan, _ = build_rollout_first_page_plan(config, regions, categories)
    plan_path = tmp_path / "plan.csv"
    plan.to_csv(plan_path, index=False)
    summary_path = tmp_path / "atlanta.json"
    summary_path.write_text(
        json.dumps(atlanta_validation_summary()),
        encoding="utf-8",
    )
    script_path = ROOT / "scripts/scrape/11a_run_business_listings_rollout_stage.py"
    spec = importlib.util.spec_from_file_location("standard_rollout_runner", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "parse_arguments",
        lambda: Namespace(
            stage="standard_rollout",
            plan=plan_path,
            settings=ROOT / "config/settings.yaml",
            results_directory=tmp_path / "results",
            large_market_summary=summary_path,
            confirm_submit=None,
        ),
    )
    assert module.main() == 0
    output = capsys.readouterr().out
    assert '"stage_requests": 20' in output
    assert '"remaining_estimated_minimum_cost_usd": 0.24' in output
    assert '"remaining_estimated_maximum_cost_usd": 7.44' in output
    assert '"credentials_read": false' in output
    assert '"api_requests_submitted": 0' in output
    assert "SUBMIT_20_PAID_BUSINESS_LISTINGS_REQUESTS" in output


def test_first_page_executor_accepts_known_continuations_in_shared_log(
    tmp_path: Path,
) -> None:
    script_path = ROOT / "scripts/scrape/11a_run_business_listings_rollout_stage.py"
    spec = importlib.util.spec_from_file_location("rollout_log_reader", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first_page = "business_listings_rollout:Atlanta_GA_L:g01:p01"
    log_path = tmp_path / "result_log.csv"
    pd.DataFrame(
        {
            "task_tag": [
                first_page,
                "business_listings_rollout:Atlanta_GA_L:g01:p02",
                "business_listings_rollout:Atlanta_GA_L:g01:p03",
                "business_listings_rollout:Atlanta_GA_L:g01:p04",
            ],
            "request_status": ["completed"] * 4,
        }
    ).to_csv(log_path, index=False)
    assert module.completed_tags(log_path, {first_page}) == {first_page}


def test_first_page_executor_rejects_unknown_continuation_parent(
    tmp_path: Path,
) -> None:
    script_path = ROOT / "scripts/scrape/11a_run_business_listings_rollout_stage.py"
    spec = importlib.util.spec_from_file_location("rollout_unknown_log_reader", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    log_path = tmp_path / "result_log.csv"
    pd.DataFrame(
        {
            "task_tag": ["business_listings_rollout:Unknown:g01:p02"],
            "request_status": ["completed"],
        }
    ).to_csv(log_path, index=False)
    with pytest.raises(ValueError, match="unexpected tags"):
        module.completed_tags(
            log_path,
            {"business_listings_rollout:Atlanta_GA_L:g01:p01"},
        )


def test_atlanta_executor_validation_submits_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config, regions, categories = inputs()
    plan, _ = build_rollout_first_page_plan(config, regions, categories)
    plan_path = tmp_path / "plan.csv"
    plan.to_csv(plan_path, index=False)
    script_path = ROOT / "scripts/scrape/11a_run_business_listings_rollout_stage.py"
    spec = importlib.util.spec_from_file_location("rollout_stage_runner", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "parse_arguments",
        lambda: Namespace(
            stage="large_market_validation",
            plan=plan_path,
            settings=ROOT / "config/settings.yaml",
            results_directory=tmp_path / "results",
            confirm_submit=None,
        ),
    )
    assert module.main() == 0
    output = capsys.readouterr().out
    assert '"credentials_read": false' in output
    assert '"api_requests_submitted": 0' in output
    assert "SUBMIT_2_PAID_BUSINESS_LISTINGS_REQUESTS" in output


def test_reference_envelope_applies_zip_rule_before_distance() -> None:
    config, regions, categories = inputs()
    plan, _ = build_rollout_first_page_plan(config, regions, categories)
    clinics = pd.DataFrame(
        {
            "clinic_key": ["inside", "wrong_zip", "missing_zip", "ineligible"],
            "search_location": ["Atlanta_GA_L"] * 4,
            "zip": [30303, 29201, None, 30303],
            "latitude": [33.75, 34.00, 33.80, 33.75],
            "longitude": [-84.39, -84.00, -84.30, -84.39],
            "spatial_analysis_eligible": [True, True, True, False],
        }
    )
    coverage, summary = audit_rollout_reference_envelope(clinics, plan, regions)
    assert coverage["clinic_key"].tolist() == ["inside"]
    assert summary["zip_valid_reference_clinics"] == 1
    assert summary["outside_planned_radius"] == 0


def test_atlanta_continuation_plan_uses_three_bounded_offsets() -> None:
    config, regions, categories = inputs()
    plan, _ = build_rollout_first_page_plan(config, regions, categories)
    atlanta = plan.loc[plan["market"].eq("Atlanta_GA_L")].sort_values("category_group")
    audit = pd.DataFrame(
        [
            {
                "task_tag": atlanta.iloc[0]["task_tag"],
                "market": "Atlanta_GA_L",
                "category_group": 1,
                "total_count": 3640,
                "returned_item_count": 1000,
                "requested_offset": 0,
                "next_offset": 1000,
                "pagination_required": True,
                "continuation_available": True,
            },
            {
                "task_tag": atlanta.iloc[1]["task_tag"],
                "market": "Atlanta_GA_L",
                "category_group": 2,
                "total_count": 482,
                "returned_item_count": 482,
                "requested_offset": 0,
                "next_offset": 482,
                "pagination_required": False,
                "continuation_available": False,
            },
        ]
    )
    continuation, summary = build_rollout_continuation_plan(
        plan,
        audit,
        request_cost_usd=0.012,
        item_cost_usd=0.00036,
    )
    assert continuation["offset"].tolist() == [1000, 2000, 3000]
    assert continuation["expected_page_items"].tolist() == [1000, 1000, 640]
    assert continuation["task_tag"].str.endswith(("p02", "p03", "p04")).all()
    assert summary["expected_remaining_items"] == 2640
    assert summary["estimated_expected_cost_usd"] == 0.9864


def test_continuation_plan_ignores_category_group_already_completed_by_saved_pages() -> None:
    config, regions, categories = inputs()
    plan, _ = build_rollout_first_page_plan(config, regions, categories)
    atlanta = plan.loc[
        plan["market"].eq("Atlanta_GA_L") & plan["category_group"].eq(1)
    ].iloc[0]
    buffalo = plan.loc[
        plan["market"].eq("Buffalo_NY_L") & plan["category_group"].eq(1)
    ].iloc[0]
    rows = []
    for page, offset, returned in [
        (1, 0, 1000),
        (2, 1000, 1000),
        (3, 2000, 1000),
        (4, 3000, 640),
    ]:
        rows.append(
            {
                "task_tag": f"{str(atlanta['task_tag'])[:-3]}p{page:02d}",
                "market": "Atlanta_GA_L",
                "category_group": 1,
                "total_count": 3640,
                "returned_item_count": returned,
                "requested_offset": offset,
                "next_offset": offset + returned,
                "pagination_required": offset + returned < 3640,
                "continuation_available": offset + returned < 3640,
            }
        )
    rows.append(
        {
            "task_tag": buffalo["task_tag"],
            "market": "Buffalo_NY_L",
            "category_group": 1,
            "total_count": 1126,
            "returned_item_count": 1000,
            "requested_offset": 0,
            "next_offset": 1000,
            "pagination_required": True,
            "continuation_available": True,
        }
    )
    continuation, summary = build_rollout_continuation_plan(
        plan,
        pd.DataFrame(rows),
        request_cost_usd=0.012,
        item_cost_usd=0.00036,
    )
    assert continuation["market"].tolist() == ["Buffalo_NY_L"]
    assert continuation["offset"].tolist() == [1000]
    assert continuation["expected_page_items"].tolist() == [126]
    assert summary["planned_continuation_requests"] == 1
