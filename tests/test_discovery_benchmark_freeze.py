"""Tests for the audited primary-discovery benchmark freeze."""

import pandas as pd
import pytest

from medical_ratings.discovery_benchmark_freeze import freeze_discovery_benchmark


MARKETS = [f"Market_{index:02d}" for index in range(15)]


def summary() -> dict[str, object]:
    return {
        "analysis_status": "reference_status_manual_adjudication_applied",
        "main_discovery_numerator_increase": 0,
        "remaining_unresolved_status_decisions": 0,
        "status_adjudication_complete": True,
        "uniform_residual_discovery_approved": False,
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
        "current_reference_units_after_status_audit": 150,
        "source_union_units_after_status_audit": 135,
        "remaining_active_reference_gaps": 15,
    }


def source_union() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "market": market,
                "reference_key": f"reference:{market}:{unit}",
                "current_reference_included_after_status_audit": True,
                "source_union_after_status_audit": unit < 9,
            }
            for market in MARKETS
            for unit in range(10)
        ]
    )


def by_market() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": MARKETS,
            "current_reference_units_after_status_audit": [10] * 15,
            "source_union_units_after_status_audit": [9] * 15,
            "source_union_recall_after_status_audit": [0.9] * 15,
            "remaining_active_reference_gaps": [1] * 15,
            "next_action_after_status_audit": ["freeze_primary_discovery"] * 15,
        }
    )


def residual_manifest() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "task_tag": f"residual:{market}:{keyword}",
                "plan_type": "uniform_residual_singleton_discovery",
                "market": market,
                "query": f"keyword {keyword}",
                "included_in_main_discovery_pipeline": True,
            }
            for market in MARKETS
            for keyword in range(5)
        ]
    )


def test_freeze_reconciles_counts_and_cancels_residual_tasks() -> None:
    active, markets, carry_forward, cancelled, frozen = freeze_discovery_benchmark(
        summary(), by_market(), source_union(), residual_manifest()
    )

    assert len(active) == 150
    assert active["source_union_after_status_audit"].sum() == 135
    assert markets["discovery_benchmark_frozen"].all()
    assert len(carry_forward) == 15
    assert carry_forward["final_discovery_role"].eq(
        "validated_legacy_carry_forward"
    ).all()
    assert not carry_forward["requires_new_paid_discovery"].any()
    assert cancelled["final_execution_status"].eq(
        "cancelled_not_needed_after_gate"
    ).all()
    assert not cancelled["paid_submission_approved"].any()
    assert frozen["uniform_residual_tasks_cancelled"] == 75
    assert frozen["validated_legacy_carry_forward_units"] == 15
    assert frozen["discovery_benchmark_is_final_competition_universe"] is False
    assert frozen["regression_balltree_modified"] is False


def test_freeze_rejects_a_market_below_gate() -> None:
    markets = by_market()
    markets.loc[0, "source_union_recall_after_status_audit"] = 0.89
    with pytest.raises(ValueError, match="below"):
        freeze_discovery_benchmark(
            summary(), markets, source_union(), residual_manifest()
        )


def test_freeze_rejects_approved_residual_search() -> None:
    bad_summary = summary()
    bad_summary["uniform_residual_discovery_approved"] = True
    with pytest.raises(ValueError, match="uniform_residual_discovery_approved"):
        freeze_discovery_benchmark(
            bad_summary, by_market(), source_union(), residual_manifest()
        )
