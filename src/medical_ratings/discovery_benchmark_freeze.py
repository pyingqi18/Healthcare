"""Freeze the audited discovery benchmark before location resolution."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd


REQUIRED_SUMMARY_VALUES = {
    "analysis_status": "reference_status_manual_adjudication_applied",
    "main_discovery_numerator_increase": 0,
    "remaining_unresolved_status_decisions": 0,
    "status_adjudication_complete": True,
    "uniform_residual_discovery_approved": False,
    "automatic_profile_or_location_merges": 0,
    "regression_balltree_modified": False,
}


def _require_columns(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def _as_bool(series: pd.Series, label: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    normalized = series.astype("string").str.strip().str.lower()
    invalid = ~normalized.isin({"true", "false"})
    if invalid.any():
        raise ValueError(f"{label} contains non-boolean values")
    return normalized.eq("true")


def freeze_discovery_benchmark(
    adjudication_summary: Mapping[str, Any],
    by_market: pd.DataFrame,
    source_union: pd.DataFrame,
    residual_manifest: pd.DataFrame,
    *,
    expected_market_count: int = 15,
    expected_residual_task_count: int = 75,
    primary_market_minimum: float = 0.90,
) -> tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]
]:
    """Validate and freeze the reference benchmark without approving more search."""

    for key, expected in REQUIRED_SUMMARY_VALUES.items():
        if adjudication_summary.get(key) != expected:
            raise ValueError(
                f"Adjudication summary {key!r} must equal {expected!r}; "
                f"received {adjudication_summary.get(key)!r}"
            )

    market_columns = {
        "market",
        "current_reference_units_after_status_audit",
        "source_union_units_after_status_audit",
        "source_union_recall_after_status_audit",
        "remaining_active_reference_gaps",
        "next_action_after_status_audit",
    }
    _require_columns(by_market, market_columns, "by-market audit")
    if len(by_market) != expected_market_count or not by_market["market"].is_unique:
        raise ValueError(
            f"By-market audit must contain {expected_market_count} unique markets"
        )
    if not by_market["next_action_after_status_audit"].eq(
        "freeze_primary_discovery"
    ).all():
        raise ValueError("Every market must be approved for primary discovery freeze")
    if (
        pd.to_numeric(
            by_market["source_union_recall_after_status_audit"], errors="raise"
        )
        < primary_market_minimum
    ).any():
        raise ValueError("At least one market remains below the frozen recall gate")

    union_columns = {
        "market",
        "reference_key",
        "current_reference_included_after_status_audit",
        "source_union_after_status_audit",
    }
    _require_columns(source_union, union_columns, "source union")
    if source_union.duplicated(["market", "reference_key"]).any():
        raise ValueError("Source union contains duplicate market-reference keys")
    union = source_union.copy()
    union["current_reference_included_after_status_audit"] = _as_bool(
        union["current_reference_included_after_status_audit"],
        "current_reference_included_after_status_audit",
    )
    union["source_union_after_status_audit"] = _as_bool(
        union["source_union_after_status_audit"], "source_union_after_status_audit"
    )
    active = union.loc[
        union["current_reference_included_after_status_audit"]
    ].copy()
    active = active.sort_values(["market", "reference_key"], ignore_index=True)

    denominator = len(active)
    discovered = int(active["source_union_after_status_audit"].sum())
    remaining = denominator - discovered
    carry_forward = active.loc[
        ~active["source_union_after_status_audit"]
    ].copy()
    carry_forward["final_discovery_role"] = "validated_legacy_carry_forward"
    carry_forward["requires_new_paid_discovery"] = False
    carry_forward = carry_forward.sort_values(
        ["market", "reference_key"], ignore_index=True
    )
    expected_counts = {
        "current_reference_units_after_status_audit": denominator,
        "source_union_units_after_status_audit": discovered,
        "remaining_active_reference_gaps": remaining,
    }
    for key, actual in expected_counts.items():
        if int(adjudication_summary.get(key, -1)) != actual:
            raise ValueError(f"Summary {key} does not reconcile with source union")

    market_denominator = int(
        pd.to_numeric(
            by_market["current_reference_units_after_status_audit"], errors="raise"
        ).sum()
    )
    market_discovered = int(
        pd.to_numeric(
            by_market["source_union_units_after_status_audit"], errors="raise"
        ).sum()
    )
    if (market_denominator, market_discovered) != (denominator, discovered):
        raise ValueError("By-market totals do not reconcile with source union")

    residual_columns = {
        "task_tag",
        "plan_type",
        "market",
        "query",
        "included_in_main_discovery_pipeline",
    }
    _require_columns(residual_manifest, residual_columns, "residual manifest")
    if residual_manifest["task_tag"].duplicated().any():
        raise ValueError("Residual manifest contains duplicate task tags")
    if len(residual_manifest) != expected_residual_task_count:
        raise ValueError(
            "Residual manifest must contain exactly "
            f"{expected_residual_task_count} tasks"
        )
    if set(residual_manifest["market"]) != set(by_market["market"]):
        raise ValueError("Residual manifest market coverage differs from frozen audit")
    if not residual_manifest["plan_type"].eq(
        "uniform_residual_singleton_discovery"
    ).all():
        raise ValueError("Residual manifest contains an unexpected plan type")
    if not _as_bool(
        residual_manifest["included_in_main_discovery_pipeline"],
        "included_in_main_discovery_pipeline",
    ).all():
        raise ValueError("Residual manifest has non-discovery tasks")
    tasks_per_market = residual_manifest.groupby("market", sort=True).size()
    if tasks_per_market.nunique() != 1:
        raise ValueError("Residual tasks are not uniform across all markets")
    keyword_sets = residual_manifest.groupby("market")["query"].agg(
        lambda values: frozenset(str(value) for value in values)
    )
    if keyword_sets.nunique() != 1:
        raise ValueError("Residual keyword scope differs across markets")

    cancelled = residual_manifest.copy()
    cancelled["final_execution_status"] = "cancelled_not_needed_after_gate"
    cancelled["cancellation_reason"] = (
        "all_15_markets_meet_primary_recall_gate_after_reference_status_audit"
    )
    cancelled["paid_submission_approved"] = False
    cancelled["api_requests_submitted_by_freeze"] = 0

    frozen_markets = by_market.sort_values("market", ignore_index=True).copy()
    frozen_markets["discovery_benchmark_frozen"] = True
    summary = {
        "analysis_status": "primary_discovery_benchmark_frozen",
        "api_requests_submitted": 0,
        "market_count": len(frozen_markets),
        "current_reference_units": denominator,
        "source_union_discovered_units": discovered,
        "source_union_recall": discovered / denominator,
        "remaining_active_reference_gaps": remaining,
        "validated_legacy_carry_forward_units": len(carry_forward),
        "markets_meeting_primary_recall_gate": len(frozen_markets),
        "primary_market_recall_gate": primary_market_minimum,
        "uniform_residual_tasks_cancelled": len(cancelled),
        "uniform_residual_discovery_final_status": "cancelled_not_needed_after_gate",
        "paid_submission_approved": False,
        "discovery_benchmark_is_final_competition_universe": False,
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
        "next_required_phase": "cross_source_profile_and_physical_location_resolution",
        "interpretation_limit": (
            "This freezes historical-reference coverage only. Raw discovered profiles "
            "still require provider eligibility, cross-source identity review, and "
            "physical competition-location resolution before final clinic counts."
        ),
    }
    return active, frozen_markets, carry_forward, cancelled, summary
