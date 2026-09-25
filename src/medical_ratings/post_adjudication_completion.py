"""Plan reference-gap review and a uniform residual discovery tier."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

import pandas as pd

from medical_ratings.business_listings_comparison import (
    build_competition_unit_references,
)


REQUIRED_UNION_COLUMNS = {
    "market",
    "reference_key",
    "current_reference_included_after_followup",
    "source_union_after_followup",
}
REQUIRED_DECISION_COLUMNS = {
    "decision_id",
    "decision_type",
    "market",
    "subject_key",
    "manual_decision",
    "decision_evidence",
}


def _clean(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip()


def _boolean(values: pd.Series, label: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False).astype(bool)
    normalized = values.astype("string").str.strip().str.casefold()
    invalid = set(normalized.dropna()) - {"true", "false", "1", "0"}
    if invalid:
        raise ValueError(f"{label} contains invalid booleans: {sorted(invalid)}")
    return normalized.isin({"true", "1"})


def _require(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = columns - set(frame.columns)
    if missing:
        raise KeyError(f"{label} is missing: {sorted(missing)}")


def _query(title: object, address: object) -> str:
    parts: list[str] = []
    for value in (title, address):
        if value is not None and not pd.isna(value):
            clean = " ".join(str(value).strip().split())
            if clean:
                parts.append(clean)
    if not parts:
        raise ValueError("A reference audit query requires a title or address")
    return " ".join(parts)


def _market_action(
    recall: float,
    *,
    primary_market_minimum: float,
    reject_market_below: float,
) -> str:
    if recall >= primary_market_minimum:
        return "freeze_primary_discovery"
    if recall >= reject_market_below:
        return "targeted_reference_status_audit"
    return "discovery_redesign_and_reference_status_audit"


def build_post_adjudication_completion_plan(
    source_union: pd.DataFrame,
    reference_crosswalk: pd.DataFrame,
    reviewed_decisions: pd.DataFrame,
    *,
    markets: Sequence[str],
    regions: Mapping[str, Mapping[str, Any]],
    residual_keywords: Sequence[str],
    primary_market_minimum: float,
    reject_market_below: float,
    maps_price_per_100_results_usd: float,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, Any],
]:
    """Build one dry-run plan after specialist manual adjudication."""

    _require(source_union, REQUIRED_UNION_COLUMNS, "Follow-up source union")
    _require(reviewed_decisions, REQUIRED_DECISION_COLUMNS, "Reviewed decisions")
    expected_markets = [str(value).strip() for value in markets]
    if len(expected_markets) != 15 or len(set(expected_markets)) != 15:
        raise ValueError("Completion planning requires 15 unique markets")
    observed_markets = set(_clean(source_union["market"]).dropna())
    if observed_markets != set(expected_markets):
        raise ValueError("Source-union markets differ from the frozen 15 markets")
    missing_regions = set(expected_markets) - set(regions)
    if missing_regions:
        raise KeyError(f"Regions are missing: {sorted(missing_regions)}")
    if not 0 < reject_market_below < primary_market_minimum <= 1:
        raise ValueError("Recall gates are invalid")
    if maps_price_per_100_results_usd <= 0:
        raise ValueError("Maps Standard price must be positive")

    union = source_union.copy()
    union["market"] = _clean(union["market"])
    union["reference_key"] = _clean(union["reference_key"])
    if union[["market", "reference_key"]].isna().any().any():
        raise ValueError("Source union contains missing market or reference key")
    if union.duplicated(["market", "reference_key"]).any():
        raise ValueError("Source union contains duplicate market-reference keys")
    union["current"] = _boolean(
        union["current_reference_included_after_followup"],
        "current_reference_included_after_followup",
    )
    union["discovered"] = _boolean(
        union["source_union_after_followup"], "source_union_after_followup"
    )

    market_rows: list[dict[str, Any]] = []
    for market in expected_markets:
        group = union.loc[union["market"].eq(market)]
        denominator = int(group["current"].sum())
        found = int((group["current"] & group["discovered"]).sum())
        if denominator == 0:
            raise ValueError(f"Market has no current reference units: {market}")
        recall = found / denominator
        action = _market_action(
            recall,
            primary_market_minimum=primary_market_minimum,
            reject_market_below=reject_market_below,
        )
        market_rows.append(
            {
                "market": market,
                "current_reference_units": denominator,
                "source_union_discovered_units": found,
                "source_union_recall": recall,
                "remaining_reference_units": denominator - found,
                "next_action": action,
                "include_in_reference_status_audit": action
                != "freeze_primary_discovery",
                "uniform_residual_discovery_scope": True,
            }
        )
    market_plan = pd.DataFrame.from_records(market_rows)

    references = build_competition_unit_references(
        reference_crosswalk, target_markets=set(expected_markets)
    ).rename(
        columns={
            "clinic_key": "reference_key",
            "search_location": "market",
            "title": "reference_title",
            "address": "reference_address",
            "zip": "reference_zip",
            "latitude": "reference_latitude",
            "longitude": "reference_longitude",
            "phone": "reference_phone",
            "domain": "reference_domain",
        }
    )
    remaining = union.loc[union["current"] & ~union["discovered"]].copy()
    reference_columns = [
        "market",
        "reference_key",
        "reference_title",
        "reference_address",
        "reference_zip",
        "reference_latitude",
        "reference_longitude",
        "reference_phone",
        "reference_domain",
        "reference_source_profile_count",
        "reference_source_clinic_keys",
        "reference_source_key_prefixes",
    ]
    remaining = remaining.merge(
        references.loc[:, reference_columns],
        on=["market", "reference_key"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if not remaining["_merge"].eq("both").all():
        missing = remaining.loc[
            remaining["_merge"].ne("both"), "reference_key"
        ].head(5)
        raise ValueError(
            "Remaining references are absent from the crosswalk: "
            + ", ".join(missing.astype(str))
        )
    remaining = remaining.drop(columns="_merge").merge(
        market_plan.loc[:, ["market", "next_action"]],
        on="market",
        how="left",
        validate="many_to_one",
    )
    remaining["reference_review_scope"] = remaining["next_action"].map(
        {
            "freeze_primary_discovery": "validated_legacy_carry_forward_inventory",
            "targeted_reference_status_audit": "paid_targeted_current_status_audit",
            "discovery_redesign_and_reference_status_audit": (
                "paid_targeted_current_status_audit_and_redesign_diagnostic"
            ),
        }
    )
    remaining = remaining.sort_values(
        ["market", "reference_title", "reference_key"], ignore_index=True
    )

    audit_scope = remaining.loc[
        remaining["next_action"].ne("freeze_primary_discovery")
    ].copy()
    audit_rows: list[dict[str, Any]] = []
    for row in audit_scope.itertuples(index=False):
        digest = hashlib.sha256(str(row.reference_key).encode("utf-8")).hexdigest()[:12]
        audit_rows.append(
            {
                "task_tag": f"reference_status_audit:{row.market}:{digest}",
                "plan_type": "historical_reference_status_audit",
                "market": row.market,
                "reference_key": row.reference_key,
                "query": _query(row.reference_title, row.reference_address),
                "location_code": int(regions[row.market]["location_code"]),
                "language_code": "en",
                "depth": 100,
                "priority": 1,
                "estimated_cost_usd": round(maps_price_per_100_results_usd, 6),
                "included_in_main_discovery_pipeline": False,
                "planning_only": True,
                "execution_enabled": False,
            }
        )
    reference_audit_manifest = pd.DataFrame.from_records(audit_rows)

    keywords = [" ".join(str(value).strip().split()) for value in residual_keywords]
    if not keywords or any(not value for value in keywords):
        raise ValueError("Residual keywords cannot be empty")
    if len(set(keywords)) != len(keywords):
        raise ValueError("Residual keywords must be unique")
    discovery_rows: list[dict[str, Any]] = []
    for market in expected_markets:
        for keyword in keywords:
            digest = hashlib.sha256(keyword.encode("utf-8")).hexdigest()[:10]
            discovery_rows.append(
                {
                    "task_tag": f"maps_residual:{market}:{digest}",
                    "plan_type": "uniform_residual_singleton_discovery",
                    "market": market,
                    "query": keyword,
                    "location_code": int(regions[market]["location_code"]),
                    "language_code": "en",
                    "depth": 100,
                    "priority": 1,
                    "estimated_cost_usd": round(
                        maps_price_per_100_results_usd, 6
                    ),
                    "included_in_main_discovery_pipeline": True,
                    "planning_only": True,
                    "execution_enabled": False,
                }
            )
    residual_manifest = pd.DataFrame.from_records(discovery_rows)
    if not residual_manifest.groupby("market").size().eq(len(keywords)).all():
        raise ValueError("Every market must receive every residual keyword")

    reviewed = reviewed_decisions.copy()
    reviewed["manual_decision"] = _clean(reviewed["manual_decision"])
    unresolved = reviewed.loc[reviewed["manual_decision"].eq("unresolved")].copy()
    unresolved = unresolved.sort_values(
        ["decision_type", "market", "subject_key"], ignore_index=True
    )

    denominator = int(union["current"].sum())
    found = int((union["current"] & union["discovered"]).sum())
    action_counts = market_plan["next_action"].value_counts()
    summary = {
        "analysis_status": "post_adjudication_gap_closure_planning_only",
        "planning_only": True,
        "paid_execution_enabled": False,
        "credentials_read": False,
        "api_requests_submitted": 0,
        "current_reference_units": denominator,
        "source_union_discovered_units": found,
        "source_union_recall": found / denominator,
        "remaining_reference_units": denominator - found,
        "unique_unresolved_decision_rows": len(unresolved),
        "markets_by_next_action": {
            str(key): int(value) for key, value in action_counts.sort_index().items()
        },
        "reference_status_audit_markets": sorted(set(audit_scope["market"])),
        "reference_status_audit_tasks": len(reference_audit_manifest),
        "reference_status_audit_estimated_cost_usd": round(
            float(reference_audit_manifest["estimated_cost_usd"].sum()), 6
        ),
        "uniform_residual_keywords": keywords,
        "uniform_residual_discovery_tasks": len(residual_manifest),
        "uniform_residual_discovery_estimated_cost_usd": round(
            float(residual_manifest["estimated_cost_usd"].sum()), 6
        ),
        "uniform_residual_discovery_status": "prepared_conditional_not_approved",
        "legacy_53_combinations_reused": False,
        "legacy_singleton_queries_reused": keywords,
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
        "next_decision": (
            "Review the reference-status manifest first. The uniform residual "
            "manifest is prepared for all 15 markets but remains conditional until "
            "the five below-gate markets are audited."
        ),
    }
    return (
        market_plan,
        remaining,
        reference_audit_manifest,
        residual_manifest,
        unresolved,
        summary,
    )
