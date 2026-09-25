"""Build specialist follow-up queues and diagnose remaining market gaps."""

from __future__ import annotations

from math import ceil
from typing import Any

import pandas as pd


COORDINATE_REVIEW = "coordinate_only_within_10m_review"
SPECIALIST_ONLY = "specialist_only_exact_profile"
MANUAL_CATEGORY = "manual_category_review"
MISSING_GEOGRAPHY = "maps_missing_zip"


def _require(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = columns - set(frame.columns)
    if missing:
        raise KeyError(f"{label} is missing: {sorted(missing)}")


def _clean_key(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    output = frame.copy()
    for column in columns:
        output[column] = output[column].astype("string").str.strip()
    return output


def _boolean(values: pd.Series, label: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False).astype(bool)
    normalized = values.astype("string").str.strip().str.casefold()
    invalid = set(normalized.dropna()) - {"true", "false", "1", "0"}
    if invalid:
        raise ValueError(f"{label} contains invalid booleans: {sorted(invalid)}")
    return normalized.isin({"true", "1"})


def build_specialist_identity_review_queue(
    remaining_references: pd.DataFrame,
    specialist_match_pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Keep every 10-metre specialist pair for still-unmatched references."""

    _require(
        remaining_references,
        {
            "market",
            "reference_key",
            "maps_specialist_best_candidate_key",
            "maps_specialist_best_matching_evidence",
        },
        "Remaining-reference table",
    )
    _require(
        specialist_match_pairs,
        {
            "market",
            "reference_key",
            "reference_title",
            "reference_address",
            "candidate_key",
            "candidate_cid",
            "candidate_title",
            "candidate_category",
            "candidate_address",
            "eligibility_review_status",
            "same_normalized_address",
            "same_phone",
            "distance_meters",
            "title_similarity",
            "matching_evidence",
            "fixed_rule_match",
        },
        "Specialist match-pair table",
    )
    remaining = _clean_key(remaining_references, ("market", "reference_key"))
    pairs = _clean_key(specialist_match_pairs, ("market", "reference_key"))
    if remaining.duplicated(["market", "reference_key"]).any():
        raise ValueError("Remaining-reference table contains duplicate keys")
    if pairs.duplicated(["market", "reference_key", "candidate_key"]).any():
        raise ValueError("Specialist match-pair table contains duplicate pairs")

    candidate_references = remaining.loc[
        remaining["maps_specialist_best_matching_evidence"].eq(COORDINATE_REVIEW),
        [
            "market",
            "reference_key",
            "maps_specialist_best_candidate_key",
        ],
    ].copy()
    queue = pairs.merge(
        candidate_references,
        on=["market", "reference_key"],
        how="inner",
        validate="many_to_one",
    )
    queue = queue.loc[queue["matching_evidence"].eq(COORDINATE_REVIEW)].copy()
    found = set(zip(queue["market"], queue["reference_key"]))
    expected = set(
        zip(candidate_references["market"], candidate_references["reference_key"])
    )
    if found != expected:
        raise ValueError("A coordinate-only reference lacks its specialist pair evidence")
    if _boolean(queue["fixed_rule_match"], "fixed_rule_match").any():
        raise ValueError("Identity-review queue unexpectedly contains a fixed-rule match")

    distance = pd.to_numeric(queue["distance_meters"], errors="coerce")
    similarity = pd.to_numeric(queue["title_similarity"], errors="coerce")
    queue = queue.assign(
        _distance=distance.fillna(float("inf")),
        _similarity=similarity.fillna(-1.0),
    ).sort_values(
        ["market", "reference_key", "_distance", "_similarity"],
        ascending=[True, True, True, False],
        ignore_index=True,
    )
    queue["candidate_rank_within_reference"] = (
        queue.groupby(["market", "reference_key"]).cumcount() + 1
    )
    queue["best_candidate_from_38a"] = queue["candidate_key"].eq(
        queue["maps_specialist_best_candidate_key"]
    )
    queue["manual_pair_decision"] = ""
    queue["decision_evidence"] = ""
    queue["evidence_url"] = ""
    queue["reviewed_by"] = ""
    queue["reviewed_on"] = ""
    queue = queue.drop(columns=["_distance", "_similarity"])
    return queue


def build_specialist_profile_review_queue(
    specialist_profile_audit: pd.DataFrame,
    specialist_exact_overlap: pd.DataFrame,
) -> pd.DataFrame:
    """Combine new ambiguous categories and missing-ZIP specialist profiles."""

    common = {
        "requested_location",
        "profile_key",
        "cid",
        "place_id",
        "title",
        "category",
        "address",
        "zip",
        "market_assignment_status",
        "eligibility_review_status",
    }
    _require(specialist_profile_audit, common, "Specialist profile audit")
    _require(
        specialist_exact_overlap,
        common | {"specialist_exact_profile_status"},
        "Specialist exact-overlap table",
    )
    profiles = _clean_key(
        specialist_profile_audit, ("requested_location", "profile_key")
    )
    overlap = _clean_key(
        specialist_exact_overlap, ("requested_location", "profile_key")
    )
    for label, frame in (("profile audit", profiles), ("exact overlap", overlap)):
        if frame.duplicated(["requested_location", "profile_key"]).any():
            raise ValueError(f"Specialist {label} contains duplicate profile keys")

    category = overlap.loc[
        overlap["specialist_exact_profile_status"].eq(SPECIALIST_ONLY)
        & overlap["eligibility_review_status"].eq(MANUAL_CATEGORY)
    ].copy()
    category["review_type"] = "specialist_only_manual_category"
    category["required_decision"] = (
        "include_dental_provider|exclude_non_dentist_category|unresolved"
    )

    geography = profiles.loc[
        profiles["market_assignment_status"].eq(MISSING_GEOGRAPHY)
    ].copy()
    geography["review_type"] = "specialist_missing_geography"
    geography["required_decision"] = (
        "eligible_target_zip|outside_target_zip|unresolved"
    )
    geography["specialist_exact_profile_status"] = "not_compared_missing_geography"

    columns = [
        "review_type",
        "required_decision",
        "requested_location",
        "profile_key",
        "cid",
        "place_id",
        "title",
        "category",
        "additional_categories_json",
        "address",
        "address_street",
        "city",
        "zip",
        "normalized_zip",
        "postal_code_status",
        "latitude",
        "longitude",
        "phone",
        "domain",
        "url",
        "observed_queries",
        "google_category_evidence",
        "legacy_category_group",
        "market_assignment_status",
        "eligibility_review_status",
        "specialist_exact_profile_status",
    ]
    available = [
        column
        for column in columns
        if column in category.columns and column in geography.columns
    ]
    queue = pd.concat(
        [category[available], geography[available]], ignore_index=True
    ).sort_values(
        ["requested_location", "review_type", "title", "profile_key"],
        ignore_index=True,
    )
    if queue.duplicated(["requested_location", "profile_key"]).any():
        raise ValueError("A specialist profile appears in multiple review rows")
    queue["manual_decision"] = ""
    queue["decision_evidence"] = ""
    queue["evidence_url"] = ""
    queue["reviewed_by"] = ""
    queue["reviewed_on"] = ""
    return queue


def build_market_gap_diagnostic(
    market_summary: pd.DataFrame,
    remaining_references: pd.DataFrame,
    identity_queue: pd.DataFrame,
    profile_queue: pd.DataFrame,
    *,
    expected_markets: set[str],
    primary_market_minimum: float,
    reject_market_below: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Show whether pending manual evidence can change each market's gate."""

    _require(
        market_summary,
        {
            "market",
            "current_reference_units",
            "source_union_after_specialist_units",
            "source_union_after_specialist_recall",
            "remaining_unmatched_reference_units",
            "benchmark_decision_after_specialist",
        },
        "Specialist market summary",
    )
    expected = {str(value).strip() for value in expected_markets}
    markets = _clean_key(market_summary, ("market",))
    if set(markets["market"].dropna().astype(str)) != expected:
        raise ValueError("Market summary differs from the frozen market set")
    if markets["market"].duplicated().any():
        raise ValueError("Market summary contains duplicate markets")
    if not 0 <= reject_market_below <= primary_market_minimum <= 1:
        raise ValueError("Recall gates are invalid")

    pending_identity = (
        identity_queue.groupby("market")["reference_key"].nunique()
        if not identity_queue.empty
        else pd.Series(dtype=int)
    )
    profile_counts = (
        profile_queue.groupby(["requested_location", "review_type"])
        .size()
        .unstack(fill_value=0)
        if not profile_queue.empty
        else pd.DataFrame()
    )
    rows: list[dict[str, Any]] = []
    for row in markets.itertuples(index=False):
        market = str(row.market)
        denominator = int(row.current_reference_units)
        discovered = int(row.source_union_after_specialist_units)
        pending = int(pending_identity.get(market, 0))
        maximum_units = min(denominator, discovered + pending)
        maximum_recall = maximum_units / denominator if denominator else 0.0
        needed_reject = max(0, ceil(reject_market_below * denominator) - discovered)
        needed_primary = max(0, ceil(primary_market_minimum * denominator) - discovered)
        current_recall = float(row.source_union_after_specialist_recall)
        if current_recall >= primary_market_minimum:
            action = "manual_cleanup_then_freeze_source_union"
        elif current_recall >= reject_market_below:
            action = "targeted_current_status_audit"
        elif maximum_recall >= reject_market_below:
            action = "complete_identity_review_before_redesign_decision"
        else:
            action = "uniform_discovery_redesign_required_after_status_audit"
        rows.append(
            {
                "market": market,
                "current_reference_units": denominator,
                "source_union_after_specialist_units": discovered,
                "source_union_after_specialist_recall": current_recall,
                "remaining_unmatched_reference_units": int(
                    row.remaining_unmatched_reference_units
                ),
                "pending_specialist_identity_reference_units": pending,
                "maximum_units_if_all_pending_identity_confirmed": maximum_units,
                "maximum_recall_if_all_pending_identity_confirmed": maximum_recall,
                "additional_matches_needed_for_reject_gate": needed_reject,
                "additional_matches_needed_for_primary_gate": needed_primary,
                "specialist_only_manual_category_profiles": int(
                    profile_counts.get(
                        "specialist_only_manual_category", pd.Series(dtype=int)
                    ).get(market, 0)
                ),
                "specialist_missing_geography_profiles": int(
                    profile_counts.get(
                        "specialist_missing_geography", pd.Series(dtype=int)
                    ).get(market, 0)
                ),
                "benchmark_decision_after_specialist": (
                    row.benchmark_decision_after_specialist
                ),
                "recommended_next_action": action,
            }
        )
    diagnostic = pd.DataFrame.from_records(rows).sort_values(
        ["source_union_after_specialist_recall", "market"], ignore_index=True
    )
    redesign = diagnostic.loc[
        diagnostic["recommended_next_action"].eq(
            "uniform_discovery_redesign_required_after_status_audit"
        ),
        "market",
    ].tolist()
    gap_audit = diagnostic.loc[
        diagnostic["source_union_after_specialist_recall"].lt(
            primary_market_minimum
        ),
        "market",
    ].tolist()
    summary = {
        "analysis_status": "specialist_followup_review_queues_built_not_final",
        "api_requests_submitted": 0,
        "market_count": len(diagnostic),
        "remaining_unmatched_reference_units": len(remaining_references),
        "specialist_identity_review_reference_units": int(
            identity_queue["reference_key"].nunique()
            if not identity_queue.empty
            else 0
        ),
        "specialist_identity_review_pair_rows": len(identity_queue),
        "specialist_profile_review_units": len(profile_queue),
        "specialist_only_manual_category_profiles": int(
            profile_queue["review_type"]
            .eq("specialist_only_manual_category")
            .sum()
            if not profile_queue.empty
            else 0
        ),
        "specialist_missing_geography_profiles": int(
            profile_queue["review_type"]
            .eq("specialist_missing_geography")
            .sum()
            if not profile_queue.empty
            else 0
        ),
        "markets_below_primary_gate": gap_audit,
        "markets_requiring_uniform_discovery_redesign": redesign,
        "uniform_discovery_redesign_triggered": bool(redesign),
        "automatic_identity_matches": 0,
        "automatic_profile_or_location_merges": 0,
        "main_discovery_method_changed": False,
        "next_required_action": (
            "Review the identity and profile queues, then apply exact manual "
            "decisions before designing one uniform 15-market discovery change."
        ),
    }
    return diagnostic, summary
