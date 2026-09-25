"""Prepare and apply one consolidated specialist follow-up adjudication."""

from __future__ import annotations

from typing import Any

import pandas as pd


IDENTITY_MATCH_DECISIONS = {
    "same_historical_location",
    "renamed_or_relocated_historical_location",
}
IDENTITY_DENOMINATOR_EXCLUSIONS = {
    "historical_reference_out_of_scope",
    "historical_location_closed",
}
IDENTITY_ALLOWED = IDENTITY_MATCH_DECISIONS | IDENTITY_DENOMINATOR_EXCLUSIONS | {
    "different_nearby_location",
    "true_discovery_gap",
    "unresolved",
}
CATEGORY_ALLOWED = {
    "include_dental_provider",
    "exclude_non_dentist_category",
    "unresolved",
}
GEOGRAPHY_ALLOWED = {
    "eligible_target_zip",
    "outside_target_zip",
    "unresolved",
}


def _require(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = columns - set(frame.columns)
    if missing:
        raise KeyError(f"{label} is missing: {sorted(missing)}")


def _clean(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip()


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _boolean(values: pd.Series, label: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False).astype(bool)
    normalized = values.astype("string").str.strip().str.casefold()
    invalid = set(normalized.dropna()) - {"true", "false", "1", "0"}
    if invalid:
        raise ValueError(f"{label} contains invalid booleans: {sorted(invalid)}")
    return normalized.isin({"true", "1"})


def build_specialist_followup_decision_template(
    identity_queue: pd.DataFrame,
    profile_queue: pd.DataFrame,
    profile_audit: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Collapse pair evidence into one editable decision row per review unit."""

    _require(
        identity_queue,
        {
            "market",
            "reference_key",
            "reference_title",
            "reference_address",
            "candidate_key",
            "candidate_title",
            "candidate_category",
            "candidate_address",
            "distance_meters",
            "title_similarity",
            "best_candidate_from_38a",
        },
        "Identity queue",
    )
    _require(
        profile_queue,
        {
            "review_type",
            "requested_location",
            "profile_key",
            "title",
            "address",
            "category",
            "google_category_evidence",
        },
        "Profile queue",
    )
    _require(
        profile_audit,
        {"requested_location", "profile_key", "category_rule_decision"},
        "Profile audit",
    )

    identity = identity_queue.copy()
    for column in ("market", "reference_key", "candidate_key"):
        identity[column] = _clean(identity[column])
    if identity.duplicated(["market", "reference_key", "candidate_key"]).any():
        raise ValueError("Identity queue contains duplicate candidate pairs")

    identity_records: list[dict[str, Any]] = []
    for (market, reference_key), group in identity.groupby(
        ["market", "reference_key"], sort=True
    ):
        best = group.loc[group["best_candidate_from_38a"].eq(True)]
        if len(best) != 1:
            raise ValueError(
                f"Identity reference {reference_key} requires one 38a best candidate"
            )
        row = best.iloc[0]
        identity_records.append(
            {
                "decision_id": f"identity:{reference_key}",
                "decision_type": "historical_identity",
                "market": market,
                "subject_key": reference_key,
                "subject_title": row["reference_title"],
                "subject_address": row["reference_address"],
                "subject_category": "",
                "google_category_evidence": "",
                "candidate_pair_count": len(group),
                "suggested_candidate_key": row["candidate_key"],
                "suggested_candidate_title": row["candidate_title"],
                "suggested_candidate_category": row["candidate_category"],
                "suggested_candidate_address": row["candidate_address"],
                "suggested_candidate_distance_meters": row["distance_meters"],
                "suggested_candidate_title_similarity": row["title_similarity"],
                "frozen_category_rule_decision": "",
                "allowed_manual_decisions": "|".join(sorted(IDENTITY_ALLOWED)),
                "manual_decision": "",
                "selected_candidate_key": "",
                "secondary_category_decision": "",
                "decision_evidence": "",
                "evidence_url": "",
                "reviewed_by": "",
                "reviewed_on": "",
            }
        )

    profiles = profile_queue.copy()
    audit = profile_audit.loc[
        :, ["requested_location", "profile_key", "category_rule_decision"]
    ].copy()
    for frame in (profiles, audit):
        frame["requested_location"] = _clean(frame["requested_location"])
        frame["profile_key"] = _clean(frame["profile_key"])
    if profiles.duplicated(["requested_location", "profile_key"]).any():
        raise ValueError("Profile queue contains duplicate market-profile keys")
    if audit.duplicated(["requested_location", "profile_key"]).any():
        raise ValueError("Profile audit contains duplicate market-profile keys")
    profiles = profiles.merge(
        audit,
        on=["requested_location", "profile_key"],
        how="left",
        validate="one_to_one",
    )

    profile_records: list[dict[str, Any]] = []
    for row in profiles.itertuples(index=False):
        if row.review_type == "specialist_only_manual_category":
            decision_type = "profile_category"
            allowed = CATEGORY_ALLOWED
        elif row.review_type == "specialist_missing_geography":
            decision_type = "profile_geography"
            allowed = GEOGRAPHY_ALLOWED
        else:
            raise ValueError(f"Unknown specialist review type: {row.review_type}")
        profile_records.append(
            {
                "decision_id": f"profile:{row.profile_key}",
                "decision_type": decision_type,
                "market": row.requested_location,
                "subject_key": row.profile_key,
                "subject_title": row.title,
                "subject_address": row.address,
                "subject_category": row.category,
                "google_category_evidence": row.google_category_evidence,
                "candidate_pair_count": 0,
                "suggested_candidate_key": "",
                "suggested_candidate_title": "",
                "suggested_candidate_category": "",
                "suggested_candidate_address": "",
                "suggested_candidate_distance_meters": pd.NA,
                "suggested_candidate_title_similarity": pd.NA,
                "frozen_category_rule_decision": row.category_rule_decision,
                "allowed_manual_decisions": "|".join(sorted(allowed)),
                "manual_decision": "",
                "selected_candidate_key": "",
                "secondary_category_decision": "",
                "decision_evidence": "",
                "evidence_url": "",
                "reviewed_by": "",
                "reviewed_on": "",
            }
        )
    template = pd.DataFrame.from_records(identity_records + profile_records)
    if template["decision_id"].duplicated().any():
        raise ValueError("Consolidated decision IDs must be unique")
    template = template.sort_values(
        ["decision_type", "market", "subject_title", "subject_key"],
        ignore_index=True,
    )
    summary = {
        "analysis_status": "specialist_followup_consolidated_decisions_prepared",
        "api_requests_submitted": 0,
        "decision_rows": len(template),
        "identity_decision_rows": int(
            template["decision_type"].eq("historical_identity").sum()
        ),
        "category_decision_rows": int(
            template["decision_type"].eq("profile_category").sum()
        ),
        "geography_decision_rows": int(
            template["decision_type"].eq("profile_geography").sum()
        ),
        "automatic_identity_matches": 0,
        "automatic_profile_or_location_merges": 0,
        "next_required_action": (
            "Fill manual_decision and review evidence in the single decision file, "
            "then rerun the same script with --decisions."
        ),
    }
    return template, summary


def _validate_decisions(
    template: pd.DataFrame,
    decisions: pd.DataFrame,
    identity_queue: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "decision_id",
        "decision_type",
        "market",
        "subject_key",
        "subject_title",
        "manual_decision",
        "selected_candidate_key",
        "secondary_category_decision",
        "decision_evidence",
        "reviewed_by",
        "reviewed_on",
    }
    _require(decisions, required, "Specialist follow-up decisions")
    reviewed = decisions.copy()
    for column in required:
        reviewed[column] = _clean(reviewed[column])
    if reviewed["decision_id"].duplicated().any():
        raise ValueError("Decision file contains duplicate decision IDs")
    expected = template.set_index("decision_id")
    actual = reviewed.set_index("decision_id")
    if set(expected.index) != set(actual.index):
        missing = sorted(set(expected.index) - set(actual.index))[:5]
        unexpected = sorted(set(actual.index) - set(expected.index))[:5]
        raise ValueError(
            f"Decision coverage differs from template; missing={missing}, "
            f"unexpected={unexpected}"
        )
    for decision_id in expected.index:
        for column in ("decision_type", "market", "subject_key", "subject_title"):
            if _text(expected.loc[decision_id, column]) != _text(
                actual.loc[decision_id, column]
            ):
                raise ValueError(f"Immutable {column} changed for {decision_id}")

    identity_candidates = (
        identity_queue.groupby(["market", "reference_key"])["candidate_key"]
        .apply(lambda values: set(_clean(values)))
        .to_dict()
    )
    for row in reviewed.itertuples(index=False):
        decision = _text(row.manual_decision)
        if not decision:
            raise ValueError(f"Blank manual decision for {row.decision_id}")
        if not _text(row.decision_evidence):
            raise ValueError(f"Blank decision evidence for {row.decision_id}")
        if not _text(row.reviewed_by) or not _text(row.reviewed_on):
            raise ValueError(f"Blank reviewer metadata for {row.decision_id}")
        if row.decision_type == "historical_identity":
            if decision not in IDENTITY_ALLOWED:
                raise ValueError(f"Invalid identity decision: {decision}")
            selected = _text(row.selected_candidate_key)
            if decision in IDENTITY_MATCH_DECISIONS:
                candidates = identity_candidates[(row.market, row.subject_key)]
                if selected not in candidates:
                    raise ValueError(
                        f"Confirmed identity {row.decision_id} requires a listed candidate"
                    )
            elif selected:
                raise ValueError(
                    f"Non-match identity {row.decision_id} cannot select a candidate"
                )
        elif row.decision_type == "profile_category":
            if decision not in CATEGORY_ALLOWED:
                raise ValueError(f"Invalid category decision: {decision}")
        elif row.decision_type == "profile_geography":
            if decision not in GEOGRAPHY_ALLOWED:
                raise ValueError(f"Invalid geography decision: {decision}")
            secondary = _text(row.secondary_category_decision)
            frozen = _text(expected.loc[row.decision_id, "frozen_category_rule_decision"])
            if decision == "eligible_target_zip" and frozen not in {
                "include",
                "exclude",
            }:
                if secondary not in CATEGORY_ALLOWED:
                    raise ValueError(
                        f"Eligible geography {row.decision_id} requires a category decision"
                    )
            elif secondary:
                raise ValueError(
                    f"Secondary category decision is not applicable to {row.decision_id}"
                )
        else:
            raise ValueError(f"Unknown decision type: {row.decision_type}")
    return reviewed.sort_values("decision_id", ignore_index=True)


def apply_specialist_followup_decisions(
    template: pd.DataFrame,
    decisions: pd.DataFrame,
    identity_queue: pd.DataFrame,
    source_union: pd.DataFrame,
    *,
    primary_market_minimum: float,
    reject_market_below: float,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, Any],
]:
    """Apply exact reviewed decisions and recalculate the current benchmark."""

    reviewed = _validate_decisions(template, decisions, identity_queue)
    _require(
        source_union,
        {
            "market",
            "reference_key",
            "current_reference_included",
            "source_union_after_specialist",
        },
        "Specialist source union",
    )
    union = source_union.copy()
    union["market"] = _clean(union["market"])
    union["reference_key"] = _clean(union["reference_key"])
    if union.duplicated(["market", "reference_key"]).any():
        raise ValueError("Specialist source union contains duplicate reference keys")
    union["current_reference_included_after_followup"] = _boolean(
        union["current_reference_included"], "current_reference_included"
    )
    union["source_union_after_followup"] = _boolean(
        union["source_union_after_specialist"], "source_union_after_specialist"
    )
    union["followup_identity_decision"] = ""
    union["followup_selected_candidate_key"] = ""

    identity = reviewed.loc[
        reviewed["decision_type"].eq("historical_identity")
    ].copy()
    union_index = union.set_index(["market", "reference_key"]).index
    for row in identity.itertuples(index=False):
        key = (row.market, row.subject_key)
        if key not in union_index:
            raise ValueError(f"Identity decision reference is absent from union: {key}")
        mask = union["market"].eq(row.market) & union["reference_key"].eq(
            row.subject_key
        )
        union.loc[mask, "followup_identity_decision"] = row.manual_decision
        union.loc[mask, "followup_selected_candidate_key"] = (
            row.selected_candidate_key
        )
        if row.manual_decision in IDENTITY_MATCH_DECISIONS:
            union.loc[mask, "source_union_after_followup"] = True
        if row.manual_decision in IDENTITY_DENOMINATOR_EXCLUSIONS:
            union.loc[mask, "current_reference_included_after_followup"] = False

    profile = reviewed.loc[
        reviewed["decision_type"].isin({"profile_category", "profile_geography"})
    ].copy()
    profile["final_market_assignment_status"] = ""
    profile["final_eligibility_review_status"] = ""
    category_mask = profile["decision_type"].eq("profile_category")
    profile.loc[category_mask, "final_market_assignment_status"] = (
        "eligible_target_zip"
    )
    profile.loc[category_mask, "final_eligibility_review_status"] = profile.loc[
        category_mask, "manual_decision"
    ]
    for index, row in profile.loc[~category_mask].iterrows():
        geography = row["manual_decision"]
        profile.loc[index, "final_market_assignment_status"] = geography
        if geography == "outside_target_zip":
            final_status = "exclude_outside_target_zip"
        elif geography == "unresolved":
            final_status = "unresolved"
        else:
            frozen = _text(
                template.set_index("decision_id").loc[
                    row["decision_id"], "frozen_category_rule_decision"
                ]
            )
            if frozen == "include":
                final_status = "include_dental_provider"
            elif frozen == "exclude":
                final_status = "exclude_non_dentist_category"
            else:
                final_status = row["secondary_category_decision"]
        profile.loc[index, "final_eligibility_review_status"] = final_status

    market_rows: list[dict[str, Any]] = []
    for market, group in union.groupby("market", sort=True):
        current = group["current_reference_included_after_followup"]
        discovered = current & group["source_union_after_followup"]
        denominator = int(current.sum())
        found = int(discovered.sum())
        recall = found / denominator if denominator else 0.0
        if recall >= primary_market_minimum:
            decision = "meets_primary_market_gate"
        elif recall >= reject_market_below:
            decision = "targeted_gap_audit_required"
        else:
            decision = "discovery_redesign_required"
        market_rows.append(
            {
                "market": market,
                "current_reference_units_after_followup": denominator,
                "source_union_units_after_followup": found,
                "source_union_recall_after_followup": recall,
                "remaining_reference_units_after_followup": denominator - found,
                "benchmark_decision_after_followup": decision,
            }
        )
    by_market = pd.DataFrame.from_records(market_rows)
    denominator = int(union["current_reference_included_after_followup"].sum())
    found = int(
        (
            union["current_reference_included_after_followup"]
            & union["source_union_after_followup"]
        ).sum()
    )
    summary = {
        "analysis_status": "specialist_followup_manual_adjudication_applied",
        "api_requests_submitted": 0,
        "reviewed_decision_rows": len(reviewed),
        "confirmed_identity_matches": int(
            identity["manual_decision"].isin(IDENTITY_MATCH_DECISIONS).sum()
        ),
        "current_reference_denominator_exclusions": int(
            identity["manual_decision"]
            .isin(IDENTITY_DENOMINATOR_EXCLUSIONS)
            .sum()
        ),
        "profile_decisions_by_final_status": {
            str(key): int(value)
            for key, value in profile["final_eligibility_review_status"]
            .value_counts()
            .sort_index()
            .items()
        },
        "current_reference_units_after_followup": denominator,
        "source_union_units_after_followup": found,
        "source_union_recall_after_followup": found / denominator,
        "remaining_reference_units_after_followup": denominator - found,
        "markets_by_decision_after_followup": {
            str(key): int(value)
            for key, value in by_market["benchmark_decision_after_followup"]
            .value_counts()
            .sort_index()
            .items()
        },
        "remaining_unresolved_decisions": int(
            reviewed["manual_decision"].eq("unresolved").sum()
        ),
        "adjudication_complete": bool(
            not reviewed["manual_decision"].eq("unresolved").any()
            and not profile["final_eligibility_review_status"].eq("unresolved").any()
        ),
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
    }
    confirmed = identity.loc[
        identity["manual_decision"].isin(IDENTITY_MATCH_DECISIONS)
    ].copy()
    return reviewed, confirmed, profile, union, by_market, summary
