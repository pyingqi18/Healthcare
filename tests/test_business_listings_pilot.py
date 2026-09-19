"""Tests for the offline Business Listings pilot design."""

from pathlib import Path

import pandas as pd
import yaml

from medical_ratings.business_listings_pilot import (
    build_business_listings_pilot_manifest,
    build_reference_coverage_audit,
    evaluate_pilot_recall,
    validate_official_categories,
)


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(relative_path: str) -> dict[str, object]:
    content = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))
    assert isinstance(content, dict)
    return content


def load_plan_inputs():
    return (
        load_yaml("config/scrape_plans.yaml"),
        load_yaml("config/regions.yaml"),
        pd.read_csv(ROOT / "config/business_listings_dental_categories.csv"),
    )


def test_selected_categories_match_official_snapshot() -> None:
    plan, _, catalog = load_plan_inputs()
    requested = plan["business_listings_pilot"]["requested_categories"]
    assert validate_official_categories(catalog, requested) == requested
    assert len(requested) == 13
    assert "oral_maxillofacial_surgeon" in requested


def test_missing_official_category_is_rejected() -> None:
    catalog = pd.DataFrame({"category_name": ["dentist"]})
    try:
        validate_official_categories(catalog, ["dentist", "orthodontist"])
    except ValueError as error:
        assert "orthodontist" in str(error)
    else:
        raise AssertionError("Missing official category was accepted")


def test_pilot_splits_thirteen_categories_into_four_requests() -> None:
    plan, regions, catalog = load_plan_inputs()
    manifest, summary = build_business_listings_pilot_manifest(
        plan, regions, catalog
    )
    assert len(manifest) == 4
    assert manifest["task_tag"].is_unique
    assert manifest.groupby("market").size().to_dict() == {
        "Malone_NY_S": 2,
        "Syracuse_NY_M": 2,
    }
    assert manifest.groupby("market")["category_count"].sum().eq(13).all()
    assert summary["planned_requests"] == 4
    assert summary["estimated_minimum_cost_usd"] == 0.048
    assert summary["estimated_maximum_cost_usd"] == 1.488


def test_pilot_manifest_cannot_enable_execution() -> None:
    plan, regions, catalog = load_plan_inputs()
    plan["business_listings_pilot"]["execution_enabled"] = True
    try:
        build_business_listings_pilot_manifest(plan, regions, catalog)
    except ValueError as error:
        assert "execution_enabled" in str(error)
    else:
        raise AssertionError("Execution-enabled pilot was accepted")


def test_reference_coverage_uses_configured_radii() -> None:
    plan, regions, _ = load_plan_inputs()
    clinics = pd.DataFrame(
        {
            "clinic_key": [
                "physical_location_final:malone",
                "physical_location_final:syracuse",
                "fallback:excluded",
            ],
            "search_location": ["Malone_NY_S", "Syracuse_NY_M", "Malone_NY_S"],
            "latitude": [44.86, 43.10, 44.8487],
            "longitude": [-74.30, -76.15, -74.2963],
        }
    )
    coverage, summary = build_reference_coverage_audit(
        clinics,
        regions,
        plan["business_listings_pilot"],
    )
    assert len(coverage) == 2
    assert summary["all_reference_clinics_inside_radius"] is True
    assert set(coverage["pilot_radius_km"]) == {5.0, 15.0}


def make_matches(malone_hits: int, syracuse_hits: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "reference_key": f"malone-{index}",
                "market": "Malone_NY_S",
                "discovered": index < malone_hits,
            }
            for index in range(10)
        ]
        + [
            {
                "reference_key": f"syracuse-{index}",
                "market": "Syracuse_NY_M",
                "discovered": index < syracuse_hits,
            }
            for index in range(100)
        ]
    )


def recall_gate() -> dict[str, float]:
    plan, _, _ = load_plan_inputs()
    return plan["business_listings_pilot"]["recall_gate"]


def test_recall_gate_approves_high_recall() -> None:
    _, summary = evaluate_pilot_recall(make_matches(10, 95), recall_gate())
    assert summary["decision"] == "approve_as_primary"


def test_recall_gate_requires_supplement_in_middle_range() -> None:
    _, summary = evaluate_pilot_recall(make_matches(9, 91), recall_gate())
    assert summary["decision"] == "maps_supplement_required"


def test_recall_gate_rejects_low_market_recall() -> None:
    _, summary = evaluate_pilot_recall(make_matches(7, 99), recall_gate())
    assert summary["decision"] == "reject_or_redesign"
