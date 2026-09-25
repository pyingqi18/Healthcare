"""Unify discovered profiles and prepare scalable physical-location review."""

from __future__ import annotations

from itertools import combinations
import math
from typing import Any

import numpy as np
import pandas as pd

from medical_ratings.business_listings_location_triage import triage_location_blocks
from medical_ratings.duplicate_candidate_audit import (
    EARTH_RADIUS_METERS,
    _distance_meters,
    _domain,
    _phone,
    _similarity,
)
from medical_ratings.identifiers import normalize_name
from medical_ratings.physical_location_groups import build_physical_location_review


COMMON_PROFILE_COLUMNS = [
    "profile_key",
    "requested_location",
    "cid",
    "place_id",
    "title",
    "category",
    "address",
    "zip",
    "latitude",
    "longitude",
    "phone",
    "domain",
    "url",
    "votes_count",
    "observation_count",
    "market_assignment_status",
    "eligibility_review_status",
]
ALLOWED_PROFILE_DECISIONS = {
    "include_dental_provider",
    "exclude_non_dentist_category",
}


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _optional_boolean(value: Any) -> bool | None:
    text = _text(value).casefold()
    if not text:
        return None
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def _first_nonblank(values: pd.Series) -> Any:
    for value in values:
        if _text(value):
            return value
    return pd.NA


def _source_rows(
    frame: pd.DataFrame,
    *,
    source_name: str,
    reviewed_profiles: pd.DataFrame | None = None,
) -> pd.DataFrame:
    required = {
        "profile_key",
        "requested_location",
        "market_assignment_status",
        "eligibility_review_status",
        "title",
        "address",
        "latitude",
        "longitude",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{source_name} is missing columns: {sorted(missing)}")
    result = frame.copy()
    if result.duplicated(["requested_location", "profile_key"]).any():
        raise ValueError(f"{source_name} contains duplicate market-profile keys")
    for column in COMMON_PROFILE_COLUMNS:
        if column not in result:
            result[column] = pd.NA
    result = result.loc[
        :,
        COMMON_PROFILE_COLUMNS
        + [
            column
            for column in ("competition_candidate_included",)
            if column in result.columns
        ],
    ].copy()
    result["profile_key"] = result["profile_key"].astype("string").str.strip()
    result["requested_location"] = (
        result["requested_location"].astype("string").str.strip()
    )
    result["profile_source"] = source_name
    result["reviewed_profile_decision"] = ""

    if reviewed_profiles is not None:
        required_review = {
            "market",
            "subject_key",
            "decision_type",
            "final_market_assignment_status",
            "final_eligibility_review_status",
        }
        missing_review = required_review - set(reviewed_profiles.columns)
        if missing_review:
            raise ValueError(
                f"Reviewed specialist profiles are missing: {sorted(missing_review)}"
            )
        reviewed = reviewed_profiles.loc[
            reviewed_profiles["decision_type"].isin(
                {"profile_category", "profile_geography"}
            ),
            [
                "market",
                "subject_key",
                "final_market_assignment_status",
                "final_eligibility_review_status",
            ],
        ].copy()
        reviewed = reviewed.rename(
            columns={"market": "requested_location", "subject_key": "profile_key"}
        )
        if reviewed.duplicated(["requested_location", "profile_key"]).any():
            raise ValueError("Reviewed specialist profiles contain duplicate keys")
        result = result.merge(
            reviewed,
            on=["requested_location", "profile_key"],
            how="left",
            validate="one_to_one",
        )
        reviewed_mask = result["final_eligibility_review_status"].notna()
        result.loc[reviewed_mask, "reviewed_profile_decision"] = result.loc[
            reviewed_mask, "final_eligibility_review_status"
        ]

    if "final_market_assignment_status" in result:
        effective_market_status = result["final_market_assignment_status"].fillna(
            result["market_assignment_status"]
        )
    else:
        effective_market_status = result["market_assignment_status"]
    result = result.loc[effective_market_status.eq("eligible_target_zip")].copy()

    source_decisions: list[str] = []
    for row in result.itertuples(index=False):
        reviewed_decision = _text(row.reviewed_profile_decision)
        if reviewed_decision == "include_dental_provider":
            source_decisions.append("reviewed_include")
            continue
        if reviewed_decision == "exclude_non_dentist_category":
            source_decisions.append("reviewed_exclude")
            continue
        explicit = _optional_boolean(
            getattr(row, "competition_candidate_included", None)
        )
        if explicit is True:
            source_decisions.append("reviewed_include")
        elif explicit is False:
            source_decisions.append("reviewed_exclude")
        elif row.eligibility_review_status == "include_dental_provider":
            source_decisions.append("automatic_include")
        else:
            source_decisions.append("needs_category_review")
    result["source_profile_decision"] = source_decisions
    return result


def _aggregate_profiles(source_rows: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for (market, profile_key), group in source_rows.groupby(
        ["requested_location", "profile_key"], sort=True
    ):
        decisions = set(group["source_profile_decision"].astype(str))
        reviewed_include = "reviewed_include" in decisions
        reviewed_exclude = "reviewed_exclude" in decisions
        if reviewed_include and reviewed_exclude:
            status = "pending_manual_review"
            reason = "conflicting_reviewed_source_decisions"
        elif reviewed_include:
            status = "include_dental_provider"
            reason = "reviewed_include_from_at_least_one_exact_profile_source"
        elif reviewed_exclude:
            status = "exclude_non_dentist_category"
            reason = "reviewed_exclude_applied_to_exact_google_profile"
        elif decisions == {"automatic_include"}:
            status = "include_dental_provider"
            reason = "all_exact_profile_sources_pass_frozen_category_rule"
        else:
            status = "pending_manual_review"
            reason = "unreviewed_or_conflicting_category_evidence"
        row: dict[str, Any] = {
            "requested_location": market,
            "profile_key": profile_key,
            "clinic_key": profile_key,
            "observed_sources": "|".join(sorted(set(group["profile_source"]))),
            "observed_source_count": int(group["profile_source"].nunique()),
            "observed_categories": "|".join(
                sorted({_text(value) for value in group["category"] if _text(value)})
            ),
            "observed_source_decisions": "|".join(sorted(decisions)),
            "preliminary_profile_status": status,
            "profile_status_basis": reason,
        }
        for column in COMMON_PROFILE_COLUMNS:
            if column in {"requested_location", "profile_key"}:
                continue
            row[column] = _first_nonblank(group[column])
        records.append(row)
    result = pd.DataFrame.from_records(records)
    if result.duplicated(["requested_location", "profile_key"]).any():
        raise AssertionError("Exact Google profile deduplication failed")
    return result.sort_values(
        ["requested_location", "profile_key"], ignore_index=True
    )


def _apply_prior_manual_profile_decisions(
    inventory: pd.DataFrame,
    prior_decisions: pd.DataFrame | None,
) -> tuple[pd.DataFrame, int, int]:
    """Reuse frozen category decisions for the same stable Google profile."""

    result = inventory.copy()
    result["prior_manual_profile_decision"] = ""
    result["prior_manual_decision_evidence"] = ""
    result["prior_manual_evidence_url"] = ""
    result["prior_manual_reviewed_on"] = ""
    if prior_decisions is None or prior_decisions.empty:
        return result, 0, 0

    required = {
        "clinic_key",
        "reviewed_title",
        "manual_decision",
        "manual_reason",
        "evidence_url",
        "evidence_checked_at_utc",
    }
    missing = required - set(prior_decisions.columns)
    if missing:
        raise ValueError(
            f"Prior manual profile decisions are missing: {sorted(missing)}"
        )
    reviewed = prior_decisions.loc[
        prior_decisions["manual_decision"].isin(ALLOWED_PROFILE_DECISIONS),
        sorted(required),
    ].copy()
    reviewed = reviewed.rename(columns={"clinic_key": "profile_key"})
    reviewed["profile_key"] = reviewed["profile_key"].astype("string").str.strip()
    if reviewed["profile_key"].isna().any() or reviewed["profile_key"].eq("").any():
        raise ValueError("Prior manual profile decisions contain blank profile keys")
    if reviewed["profile_key"].duplicated().any():
        raise ValueError("Prior manual profile decisions contain duplicate profile keys")

    current = result.set_index("profile_key", drop=False)
    reviewed = reviewed.set_index("profile_key", drop=False)
    overlapping = sorted(set(current.index) & set(reviewed.index))
    reused = 0
    pending_resolved = 0
    for profile_key in overlapping:
        current_title = normalize_name(current.at[profile_key, "title"])
        reviewed_title = normalize_name(reviewed.at[profile_key, "reviewed_title"])
        if current_title and reviewed_title and current_title != reviewed_title:
            raise ValueError(
                f"Prior manual decision title mismatch for {profile_key}"
            )
        if current.at[profile_key, "preliminary_profile_status"] == "pending_manual_review":
            pending_resolved += 1
        current.at[profile_key, "preliminary_profile_status"] = reviewed.at[
            profile_key, "manual_decision"
        ]
        current.at[profile_key, "profile_status_basis"] = (
            "prior_manual_profile_decision_reused"
        )
        current.at[profile_key, "prior_manual_profile_decision"] = reviewed.at[
            profile_key, "manual_decision"
        ]
        current.at[profile_key, "prior_manual_decision_evidence"] = reviewed.at[
            profile_key, "manual_reason"
        ]
        current.at[profile_key, "prior_manual_evidence_url"] = reviewed.at[
            profile_key, "evidence_url"
        ]
        current.at[profile_key, "prior_manual_reviewed_on"] = reviewed.at[
            profile_key, "evidence_checked_at_utc"
        ]
        reused += 1
    return current.reset_index(drop=True), reused, pending_resolved


def _apply_unanimous_frozen_category_exclusions(
    inventory: pd.DataFrame,
    category_rules: pd.DataFrame | None,
) -> tuple[pd.DataFrame, int]:
    """Exclude pending profiles only when every observed category is frozen exclude."""

    result = inventory.copy()
    result["frozen_category_exclusion_applied"] = False
    result["frozen_category_exclusion_reasons"] = ""
    if category_rules is None or category_rules.empty:
        return result, 0
    required = {"category", "category_decision", "reason"}
    missing = required - set(category_rules.columns)
    if missing:
        raise ValueError(f"Category rules are missing: {sorted(missing)}")
    rules = category_rules.copy()
    rules["category_key"] = rules["category"].astype("string").str.strip().str.casefold()
    if rules["category_key"].duplicated().any():
        raise ValueError("Category rules contain duplicate normalized categories")
    lookup = {
        str(row.category_key): (str(row.category_decision), str(row.reason))
        for row in rules.itertuples(index=False)
    }

    applied = 0
    for index, row in result.iterrows():
        if row["preliminary_profile_status"] != "pending_manual_review":
            continue
        categories = sorted(
            {
                item.strip()
                for item in _text(row["observed_categories"]).split("|")
                if item.strip()
            }
        )
        matched = [lookup.get(category.casefold()) for category in categories]
        if not categories or any(rule is None for rule in matched):
            continue
        if {rule[0] for rule in matched if rule is not None} != {"exclude"}:
            continue
        result.at[index, "preliminary_profile_status"] = (
            "exclude_non_dentist_category"
        )
        result.at[index, "profile_status_basis"] = (
            "all_observed_categories_have_frozen_exclude_rules"
        )
        result.at[index, "frozen_category_exclusion_applied"] = True
        result.at[index, "frozen_category_exclusion_reasons"] = " || ".join(
            f"{category}: {rule[1]}"
            for category, rule in zip(categories, matched)
            if rule is not None
        )
        applied += 1
    return result, applied


def _build_profile_decision_template(inventory: pd.DataFrame) -> pd.DataFrame:
    pending = inventory.loc[
        inventory["preliminary_profile_status"].eq("pending_manual_review")
    ].copy()
    selected = pending.loc[
        :,
        [
            "requested_location",
            "profile_key",
            "title",
            "address",
            "observed_sources",
            "observed_categories",
            "observed_source_decisions",
            "profile_status_basis",
        ],
    ].rename(columns={"requested_location": "market"})
    selected.insert(
        0,
        "decision_id",
        "profile:" + selected["market"].astype(str) + ":" + selected["profile_key"].astype(str),
    )
    selected["allowed_manual_decisions"] = "|".join(
        sorted(ALLOWED_PROFILE_DECISIONS)
    )
    selected["manual_decision"] = ""
    selected["decision_evidence"] = ""
    selected["evidence_url"] = ""
    selected["reviewed_by"] = ""
    selected["reviewed_on"] = ""
    return selected.sort_values(
        ["market", "title", "profile_key"], ignore_index=True
    )


def _build_carry_forward(
    carry_forward_inventory: pd.DataFrame,
    reference_universe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required_carry = {"market", "reference_key", "final_discovery_role"}
    missing_carry = required_carry - set(carry_forward_inventory.columns)
    if missing_carry:
        raise ValueError(f"Carry-forward inventory is missing: {sorted(missing_carry)}")
    required_reference = {
        "clinic_key",
        "search_location",
        "title",
        "address",
        "zip",
        "latitude",
        "longitude",
        "phone",
        "domain",
        "reference_source_clinic_keys",
    }
    missing_reference = required_reference - set(reference_universe.columns)
    if missing_reference:
        raise ValueError(f"Reference universe is missing: {sorted(missing_reference)}")
    references = reference_universe.loc[:, sorted(required_reference)].rename(
        columns={"clinic_key": "reference_key", "search_location": "market"}
    )
    if references.duplicated(["market", "reference_key"]).any():
        raise ValueError("Reference universe contains duplicate reference keys")
    joined = carry_forward_inventory.loc[:, sorted(required_carry)].merge(
        references,
        on=["market", "reference_key"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if not joined["_merge"].eq("both").all():
        raise ValueError("Carry-forward references are absent from reference universe")
    joined = joined.drop(columns="_merge")
    anchors = joined.copy()
    anchors["clinic_key"] = "legacy_anchor:" + anchors["reference_key"].astype(str)
    anchors["profile_key"] = pd.NA
    anchors["cid"] = pd.NA
    anchors["place_id"] = pd.NA
    anchors["category"] = "validated_legacy_carry_forward"
    anchors["url"] = pd.NA
    anchors["votes_count"] = 0
    anchors["observation_count"] = 1
    anchors["mapped_location"] = anchors["market"]
    anchors["final_included"] = True
    anchors["outcome_profile_included"] = False
    anchors["profile_resolution_source"] = "validated_legacy_carry_forward"
    anchors["carry_forward_acceptance_basis"] = (
        "frozen_market_recall_gate_not_individual_current_status_confirmation"
    )
    anchors["current_status_individually_verified"] = False
    anchors["current_status_sensitivity_required"] = True

    lineage_records: list[dict[str, str]] = []
    for row in joined.itertuples(index=False):
        for clinic_key in _text(row.reference_source_clinic_keys).split("|"):
            if clinic_key:
                lineage_records.append(
                    {
                        "market": str(row.market),
                        "reference_key": str(row.reference_key),
                        "legacy_outcome_clinic_key": clinic_key,
                        "outcome_identity_action": (
                            "retain_existing_profile_identity_no_rating_merge"
                        ),
                    }
                )
    lineage = pd.DataFrame.from_records(lineage_records)
    return anchors, lineage


def build_cross_source_profile_review(
    business_profiles: pd.DataFrame,
    core_maps_profiles: pd.DataFrame,
    specialist_profiles: pd.DataFrame,
    reviewed_specialist_profiles: pd.DataFrame,
    carry_forward_inventory: pd.DataFrame,
    reference_universe: pd.DataFrame,
    *,
    expected_markets: set[str],
    prior_manual_profile_decisions: pd.DataFrame | None = None,
    category_rules: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Build one exact-profile inventory and the remaining manual decision file."""

    expected = {str(value).strip() for value in expected_markets}
    if len(expected) != 15:
        raise ValueError("Expected market set must contain exactly 15 markets")
    sources = [
        _source_rows(business_profiles, source_name="business_listings"),
        _source_rows(core_maps_profiles, source_name="maps_core"),
        _source_rows(
            specialist_profiles,
            source_name="maps_specialist",
            reviewed_profiles=reviewed_specialist_profiles,
        ),
    ]
    for source in sources:
        actual = set(source["requested_location"].dropna().astype(str))
        if not actual.issubset(expected):
            raise ValueError("A profile source contains an unexpected market")
    source_rows = pd.concat(sources, ignore_index=True, sort=False)
    inventory = _aggregate_profiles(source_rows)
    (
        inventory,
        reused_prior_decisions,
        prior_pending_profiles_resolved,
    ) = _apply_prior_manual_profile_decisions(
        inventory, prior_manual_profile_decisions
    )
    inventory, frozen_category_exclusions = (
        _apply_unanimous_frozen_category_exclusions(inventory, category_rules)
    )
    actual_inventory = set(inventory["requested_location"].dropna().astype(str))
    if actual_inventory != expected:
        raise ValueError("Unified profile inventory does not cover all 15 markets")
    decisions = _build_profile_decision_template(inventory)
    anchors, lineage = _build_carry_forward(
        carry_forward_inventory, reference_universe
    )
    counts = inventory["preliminary_profile_status"].value_counts()
    summary = {
        "analysis_status": "cross_source_profile_review_prepared_not_final",
        "api_requests_submitted": 0,
        "source_profile_rows": len(source_rows),
        "exact_google_profiles": len(inventory),
        "exact_profile_duplicates_removed": len(source_rows) - len(inventory),
        "profiles_by_preliminary_status": {
            str(key): int(value) for key, value in counts.items()
        },
        "manual_profile_decisions_required": len(decisions),
        "prior_manual_profile_decisions_reused": reused_prior_decisions,
        "prior_manual_pending_profiles_resolved": prior_pending_profiles_resolved,
        "frozen_category_exclusions_applied": frozen_category_exclusions,
        "validated_legacy_carry_forward_locations": len(anchors),
        "legacy_outcome_profile_lineage_rows": len(lineage),
        "automatic_physical_location_merges": 0,
        "regression_balltree_modified": False,
        "next_required_action": (
            "Complete the consolidated profile decision file, then rerun this stage "
            "to build scalable physical-location review blocks."
        ),
    }
    return inventory, decisions, anchors, lineage, summary


def _validate_profile_decisions(
    template: pd.DataFrame, decisions: pd.DataFrame
) -> pd.DataFrame:
    required = set(template.columns)
    missing = required - set(decisions.columns)
    if missing:
        raise ValueError(f"Profile decisions are missing: {sorted(missing)}")
    if template["decision_id"].duplicated().any() or decisions["decision_id"].duplicated().any():
        raise ValueError("Profile decision IDs must be unique")
    expected = template.set_index("decision_id").sort_index()
    reviewed = (
        decisions.loc[:, template.columns].copy().set_index("decision_id").sort_index()
    )
    if set(expected.index) != set(reviewed.index):
        raise ValueError("Profile decisions must exactly cover the prepared template")
    editable = {
        "manual_decision",
        "decision_evidence",
        "evidence_url",
        "reviewed_by",
        "reviewed_on",
    }
    for column in set(template.columns) - editable - {"decision_id"}:
        if not expected[column].fillna("").astype(str).equals(
            reviewed[column].fillna("").astype(str)
        ):
            raise ValueError(f"Immutable profile decision column changed: {column}")
    for decision_id, row in reviewed.iterrows():
        decision = _text(row["manual_decision"])
        if decision not in ALLOWED_PROFILE_DECISIONS:
            raise ValueError(f"Invalid or blank decision for {decision_id}")
        if not _text(row["decision_evidence"]):
            raise ValueError(f"Blank evidence for {decision_id}")
        if not _text(row["reviewed_by"]) or not _text(row["reviewed_on"]):
            raise ValueError(f"Blank reviewer metadata for {decision_id}")
    return reviewed.reset_index().sort_values("decision_id", ignore_index=True)


def _blocked_pair_keys(candidates: pd.DataFrame) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    indexed = candidates.reset_index(drop=True)
    for column, normalizer in (
        ("address", normalize_name),
        ("phone", _phone),
        ("domain", lambda value: _domain(value, None)),
    ):
        groups: dict[tuple[str, str], list[int]] = {}
        for index, row in indexed.iterrows():
            value = normalizer(row[column])
            if value:
                groups.setdefault((str(row["mapped_location"]), value), []).append(index)
        for indices in groups.values():
            if len(indices) <= 50:
                pairs.update(tuple(sorted(pair)) for pair in combinations(indices, 2))

    try:
        from sklearn.neighbors import BallTree
    except ImportError as error:
        raise ImportError(
            "scikit-learn is required for scalable location-pair construction"
        ) from error
    for _, group in indexed.groupby("mapped_location", sort=True):
        latitude = pd.to_numeric(group["latitude"], errors="coerce")
        longitude = pd.to_numeric(group["longitude"], errors="coerce")
        valid = latitude.between(-90, 90) & longitude.between(-180, 180)
        valid_group = group.loc[valid]
        if len(valid_group) < 2:
            continue
        coordinates = np.radians(
            np.column_stack(
                [latitude.loc[valid].to_numpy(), longitude.loc[valid].to_numpy()]
            )
        )
        tree = BallTree(coordinates, metric="haversine")
        neighbors = tree.query_radius(coordinates, r=500.0 / EARTH_RADIUS_METERS)
        source_indices = list(valid_group.index)
        for left_position, right_positions in enumerate(neighbors):
            for right_position in right_positions:
                if int(right_position) <= left_position:
                    continue
                pairs.add(
                    tuple(
                        sorted(
                            (
                                int(source_indices[left_position]),
                                int(source_indices[int(right_position)]),
                            )
                        )
                    )
                )
    return pairs


def build_scalable_location_pairs(candidates: pd.DataFrame) -> pd.DataFrame:
    """Build candidate pairs from exact-identity blocks and a 500m BallTree."""

    indexed = candidates.reset_index(drop=True)
    records: list[dict[str, Any]] = []
    for left_index, right_index in sorted(_blocked_pair_keys(indexed)):
        left = indexed.iloc[left_index]
        right = indexed.iloc[right_index]
        if _text(left["mapped_location"]) != _text(right["mapped_location"]):
            continue
        same_phone = _phone(left["phone"]) is not None and _phone(left["phone"]) == _phone(right["phone"])
        same_domain = _domain(left["domain"], left["url"]) is not None and _domain(left["domain"], left["url"]) == _domain(right["domain"], right["url"])
        left_address = normalize_name(left["address"])
        right_address = normalize_name(right["address"])
        same_address = left_address is not None and left_address == right_address
        distance = _distance_meters(left, right)
        similarity = _similarity(left["title"], right["title"])
        close_50 = distance is not None and distance <= 50
        close_500 = distance is not None and distance <= 500
        should_review = (
            same_address
            or (close_50 and (same_phone or same_domain or similarity >= 0.55))
            or (same_phone and same_domain)
            or (same_phone and similarity >= 0.55)
            or (same_domain and similarity >= 0.55)
            or (close_500 and similarity >= 0.90)
        )
        if not should_review:
            continue
        high = (
            (same_address or close_50)
            and (same_phone or same_domain or similarity >= 0.55)
        ) or (same_phone and same_domain and similarity >= 0.40)
        records.append(
            {
                "left_clinic_key": left["clinic_key"],
                "left_cid": left["cid"],
                "left_title": left["title"],
                "left_address": left["address"],
                "right_clinic_key": right["clinic_key"],
                "right_cid": right["cid"],
                "right_title": right["title"],
                "right_address": right["address"],
                "mapped_location": left["mapped_location"],
                "same_phone": same_phone,
                "same_domain": same_domain,
                "same_address": same_address,
                "within_50_meters": close_50,
                "distance_meters": None if distance is None else round(distance, 1),
                "title_similarity": round(similarity, 4),
                "evidence_count": sum((same_phone, same_domain, same_address, close_50)),
                "review_priority": "high" if high else "standard",
                "review_decision": "pending_manual_review",
            }
        )
    return pd.DataFrame.from_records(
        records,
        columns=[
            "left_clinic_key", "left_cid", "left_title", "left_address",
            "right_clinic_key", "right_cid", "right_title", "right_address",
            "mapped_location", "same_phone", "same_domain", "same_address",
            "within_50_meters", "distance_meters", "title_similarity",
            "evidence_count", "review_priority", "review_decision",
        ],
    )


def apply_profile_decisions_and_build_location_review(
    inventory: pd.DataFrame,
    template: pd.DataFrame,
    decisions: pd.DataFrame,
    carry_forward_anchors: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, Any],
]:
    """Apply profile decisions and prepare review-only physical-location blocks."""

    reviewed = _validate_profile_decisions(template, decisions)
    decision_map = reviewed.set_index("decision_id")["manual_decision"]
    profiles = inventory.copy()
    profiles["decision_id"] = (
        "profile:"
        + profiles["requested_location"].astype(str)
        + ":"
        + profiles["profile_key"].astype(str)
    )
    profiles["final_profile_status"] = profiles["preliminary_profile_status"]
    pending = profiles["preliminary_profile_status"].eq("pending_manual_review")
    profiles.loc[pending, "final_profile_status"] = profiles.loc[
        pending, "decision_id"
    ].map(decision_map)
    if profiles.loc[pending, "final_profile_status"].isna().any():
        raise ValueError("A pending profile lacks a validated manual decision")
    included = profiles.loc[
        profiles["final_profile_status"].eq("include_dental_provider")
    ].copy()
    included["mapped_location"] = included["requested_location"]
    included["final_included"] = True
    included["outcome_profile_included"] = True
    included["profile_resolution_source"] = "cross_source_google_profile"
    for column, default in (
        ("cid", pd.NA), ("url", pd.NA), ("votes_count", 0),
        ("observation_count", 1), ("domain", pd.NA), ("phone", pd.NA),
    ):
        if column not in included:
            included[column] = default
        included[column] = included[column].fillna(default)

    location_columns = sorted(
        set(included.columns) | set(carry_forward_anchors.columns)
    )
    profile_candidates = included.reindex(columns=location_columns)
    carry_candidates = carry_forward_anchors.reindex(columns=location_columns)
    candidates = pd.concat(
        [profile_candidates, carry_candidates], ignore_index=True, sort=False
    )
    if candidates["clinic_key"].duplicated().any():
        raise ValueError("Location candidates contain duplicate clinic keys")
    pairs = build_scalable_location_pairs(candidates)
    blocks = build_physical_location_review(candidates, pairs)
    triage, block_profiles, triage_summary = triage_location_blocks(blocks, pairs)
    summary = {
        "analysis_status": "cross_source_location_review_blocks_prepared_not_final",
        "api_requests_submitted": 0,
        "reviewed_profile_decisions": len(reviewed),
        "included_google_profiles": len(included),
        "excluded_google_profiles": int(
            profiles["final_profile_status"].eq("exclude_non_dentist_category").sum()
        ),
        "legacy_carry_forward_location_anchors": len(carry_forward_anchors),
        "location_candidate_rows": len(candidates),
        "candidate_pairs": len(pairs),
        "provisional_location_blocks": int(blocks["physical_location_group"].nunique()),
        "multi_profile_review_blocks": len(triage),
        "blocks_by_review_tier": triage_summary["blocks_by_review_tier"],
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
        "location_pair_algorithm": "exact_identity_blocks_plus_market_500m_balltree",
        "next_required_action": (
            "Review every multi-profile block before assigning final competition "
            "location IDs; outcome profile identities remain separate."
        ),
    }
    return reviewed, profiles, included, pairs, blocks, triage, block_profiles, summary
