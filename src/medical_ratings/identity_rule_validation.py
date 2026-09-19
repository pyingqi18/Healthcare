"""Build a manual validation queue for broader historical identity evidence."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from medical_ratings.identifiers import normalize_name


SOURCE_NAMES = ("business_listings", "maps_standard")
STREET_NUMBER_PATTERN = re.compile(r"\b\d+[a-z]?\b", re.IGNORECASE)


def _street_number(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    match = STREET_NUMBER_PATTERN.search(str(value).casefold())
    return match.group(0) if match else None


def _similarity(left: object, right: object) -> float:
    clean_left = normalize_name(left)
    clean_right = normalize_name(right)
    if not clean_left or not clean_right:
        return 0.0
    return SequenceMatcher(None, clean_left, clean_right).ratio()


def _source_evidence(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    required = {
        "reference_title",
        "reference_address",
        f"{source}_best_candidate_key",
        f"{source}_best_candidate_title",
        f"{source}_best_candidate_address",
        f"{source}_best_distance_meters",
        f"{source}_best_title_similarity",
    }
    missing = required - set(frame.columns)
    if missing:
        raise KeyError(f"Review queue lacks {source} evidence: {sorted(missing)}")
    candidate_title = frame[f"{source}_best_candidate_title"]
    candidate_address = frame[f"{source}_best_candidate_address"]
    distance = pd.to_numeric(
        frame[f"{source}_best_distance_meters"], errors="coerce"
    )
    title_similarity = pd.to_numeric(
        frame[f"{source}_best_title_similarity"], errors="coerce"
    ).fillna(0.0)
    reference_title = frame["reference_title"].map(normalize_name)
    normalized_candidate_title = candidate_title.map(normalize_name)
    exact_title = (
        reference_title.notna()
        & normalized_candidate_title.notna()
        & reference_title.eq(normalized_candidate_title)
    )
    reference_number = frame["reference_address"].map(_street_number)
    candidate_number = candidate_address.map(_street_number)
    same_number = (
        reference_number.notna()
        & candidate_number.notna()
        & reference_number.eq(candidate_number)
    )
    address_similarity = pd.Series(
        [
            _similarity(left, right)
            for left, right in zip(frame["reference_address"], candidate_address)
        ],
        index=frame.index,
        dtype=float,
    )
    exact_title_100 = exact_title & distance.le(100).fillna(False)
    high_title_same_number_100 = (
        title_similarity.ge(0.8)
        & same_number
        & distance.le(100).fillna(False)
    )
    moderate_title_high_address_100 = (
        title_similarity.ge(0.6)
        & address_similarity.ge(0.8)
        & same_number
        & distance.le(100).fillna(False)
    )
    output = pd.DataFrame(index=frame.index)
    output[f"{source}_normalized_exact_title"] = exact_title
    output[f"{source}_same_street_number"] = same_number
    output[f"{source}_address_similarity"] = address_similarity.round(4)
    output[f"{source}_rule_exact_title_within_100m"] = exact_title_100
    output[f"{source}_rule_high_title_same_number_within_100m"] = (
        high_title_same_number_100
    )
    output[f"{source}_rule_moderate_title_high_address_within_100m"] = (
        moderate_title_high_address_100
    )
    output[f"{source}_candidate_rule_match"] = (
        exact_title_100
        | high_title_same_number_100
        | moderate_title_high_address_100
    )
    output[f"{source}_evidence_score"] = (
        exact_title.astype(float) * 100
        + title_similarity * 20
        + address_similarity * 10
        + same_number.astype(float) * 5
        - distance.clip(upper=1000).fillna(1000) / 1000
    ).round(4)
    return output


def build_identity_rule_validation(
    review_queue: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Create evidence columns and a manual decision file without applying matches."""

    required = {
        "market",
        "reference_key",
        "reference_title",
        "reference_address",
        "nearest_candidate_distance_meters",
        "review_tier",
        "review_priority",
    }
    missing = required - set(review_queue.columns)
    if missing:
        raise KeyError(f"Review queue is missing: {sorted(missing)}")
    if review_queue.duplicated(["market", "reference_key"]).any():
        raise ValueError("Review queue contains duplicate market-reference keys")
    frame = review_queue.copy()
    for source in SOURCE_NAMES:
        evidence = _source_evidence(frame, source)
        frame = pd.concat([frame, evidence], axis=1)
    frame["candidate_rule_match"] = False
    for source in SOURCE_NAMES:
        frame["candidate_rule_match"] |= frame[f"{source}_candidate_rule_match"]

    best_sources: list[str] = []
    reasons: list[str] = []
    for row in frame.itertuples(index=False):
        scores = {
            source: float(getattr(row, f"{source}_evidence_score"))
            for source in SOURCE_NAMES
        }
        best_source = max(scores, key=scores.get)
        best_sources.append(best_source)
        row_reasons: list[str] = []
        for source in SOURCE_NAMES:
            if getattr(row, f"{source}_rule_exact_title_within_100m"):
                row_reasons.append(f"{source}:exact_title_within_100m")
            if getattr(row, f"{source}_rule_high_title_same_number_within_100m"):
                row_reasons.append(
                    f"{source}:high_title_same_number_within_100m"
                )
            if getattr(
                row, f"{source}_rule_moderate_title_high_address_within_100m"
            ):
                row_reasons.append(
                    f"{source}:moderate_title_high_address_within_100m"
                )
        reasons.append("|".join(row_reasons))
    frame["best_evidence_source"] = best_sources
    frame["candidate_rule_reasons"] = reasons

    distance = pd.to_numeric(
        frame["nearest_candidate_distance_meters"], errors="coerce"
    )
    frame["validation_tier"] = "no_nearby_candidate"
    frame.loc[distance.le(500).fillna(False), "validation_tier"] = (
        "nearby_weak_identity"
    )
    frame.loc[distance.le(100).fillna(False), "validation_tier"] = (
        "close_weak_identity"
    )
    frame.loc[frame["candidate_rule_match"], "validation_tier"] = (
        "candidate_rule_manual_validation"
    )
    frame["proposed_decision"] = ""
    frame["decision_evidence"] = ""
    frame["reviewed_by"] = ""
    frame["reviewed_on"] = ""

    candidates = frame.loc[frame["candidate_rule_match"]].copy()
    summary = {
        "analysis_status": "broader_identity_rule_manual_validation_not_final",
        "api_requests_submitted": 0,
        "input_unmatched_reference_units": len(frame),
        "candidate_rule_manual_validation_units": len(candidates),
        "remaining_without_candidate_rule": len(frame) - len(candidates),
        "validation_tiers": {
            str(key): int(value)
            for key, value in frame["validation_tier"].value_counts().items()
        },
        "candidate_rule_components": {
            "normalized_exact_title_within_100m": int(
                pd.concat(
                    [
                        frame[f"{source}_rule_exact_title_within_100m"]
                        for source in SOURCE_NAMES
                    ],
                    axis=1,
                ).any(axis=1).sum()
            ),
            "title_similarity_at_least_0p8_same_street_number_within_100m": int(
                pd.concat(
                    [
                        frame[
                            f"{source}_rule_high_title_same_number_within_100m"
                        ]
                        for source in SOURCE_NAMES
                    ],
                    axis=1,
                ).any(axis=1).sum()
            ),
            "title_similarity_at_least_0p6_address_similarity_at_least_0p8_same_street_number_within_100m": int(
                pd.concat(
                    [
                        frame[
                            f"{source}_rule_moderate_title_high_address_within_100m"
                        ]
                        for source in SOURCE_NAMES
                    ],
                    axis=1,
                ).any(axis=1).sum()
            ),
        },
        "allowed_proposed_decisions": [
            "same_historical_location",
            "renamed_or_relocated_historical_location",
            "different_nearby_location",
            "historical_reference_out_of_scope",
            "historical_location_closed",
            "true_discovery_gap",
            "unresolved",
        ],
        "automatic_identity_matches": 0,
        "automatic_profile_or_location_merges": 0,
        "next_required_action": "Manually validate candidate-rule rows before changing the frozen matcher.",
    }
    return frame, candidates, summary
