"""Tests for the planning-only full-market scrape profile."""

from pathlib import Path

import yaml

from medical_ratings.scrape_plan import build_scrape_profile_plan


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(relative_path: str) -> dict[str, object]:
    content = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))
    assert isinstance(content, dict)
    return content


def build_plan():
    return build_scrape_profile_plan(
        load_yaml("config/scrape_plans.yaml"),
        load_yaml("config/regions.yaml"),
        profile_name="existing_15_markets_planning_v1",
    )


def test_profile_covers_the_existing_fifteen_markets() -> None:
    plan, summary = build_plan()
    assert summary["market_count"] == 15
    assert set(summary["markets"]) == set(
        load_yaml("config/regions.yaml")["regions"]
    )
    assert plan["market"].nunique() == 15


def test_profile_is_planning_only() -> None:
    _, summary = build_plan()
    assert summary["planning_only"] is True
    assert summary["execution_enabled"] is False
    assert summary["api_credentials_read"] is False
    assert summary["api_requests_submitted"] == 0


def test_legacy_reference_preserves_task_count_and_cost() -> None:
    _, summary = build_plan()
    legacy = summary["legacy_reference"]
    assert legacy["tasks_per_market"] == 106
    assert legacy["total_tasks"] == 1590
    assert legacy["estimated_total_cost_usd"] == 2.862


def test_proposed_plan_starts_with_two_market_validation() -> None:
    _, summary = build_plan()
    pilot = summary["proposed_phases"][
        "business_listings_two_market_validation"
    ]
    assert pilot["market_count"] == 2
    assert pilot["planned_tasks"] == 4
    assert pilot["estimated_minimum_cost_usd"] == 0.048
    assert pilot["estimated_maximum_cost_usd"] == 1.488


def test_keyword_supplements_use_single_queries() -> None:
    plan, _ = build_plan()
    keyword_rows = plan[plan["discovery_method"].eq("google_maps_standard")]
    assert keyword_rows["keywords"].str.contains(r"\+").sum() == 0
    assert keyword_rows.groupby("phase_id")["planned_tasks"].first().to_dict() == {
        "maps_core_keyword_supplement": 2,
        "maps_residual_singleton_redesign": 5,
        "maps_specialist_keyword_supplement": 5,
    }


def test_full_rollout_and_supplements_remain_conditional() -> None:
    plan, _ = build_plan()
    non_pilot = plan[
        ~plan["phase_id"].eq("business_listings_two_market_validation")
    ]
    assert set(non_pilot["phase_status"]) == {"conditional_not_approved"}


def test_profile_rejects_execution_enabled() -> None:
    plan_config = load_yaml("config/scrape_plans.yaml")
    regions_config = load_yaml("config/regions.yaml")
    plan_config["profiles"]["existing_15_markets_planning_v1"][
        "execution_enabled"
    ] = True
    try:
        build_scrape_profile_plan(
            plan_config,
            regions_config,
            profile_name="existing_15_markets_planning_v1",
        )
    except ValueError as error:
        assert "disable execution" in str(error)
    else:
        raise AssertionError("Execution-enabled planning profile was accepted")
