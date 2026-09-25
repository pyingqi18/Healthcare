"""Apply the complete profile-eligibility freeze to stage 46a location review."""

from __future__ import annotations

from typing import Any

import pandas as pd

from medical_ratings.cross_source_profile_resolution import (
    apply_profile_decisions_and_build_location_review,
)
from medical_ratings.profile_eligibility_audit_freeze import (
    ALLOWED_DECISIONS,
    DECISION_COLUMN_ORDER,
    merge_verified_decisions,
)


FINAL_REVIEW_COLUMNS = [
    "manual_decision",
    "decision_evidence",
    "evidence_url",
    "reviewed_by",
    "reviewed_on",
]
IDENTITY_COLUMNS = ["market", "profile_key", "title", "address"]


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        result[column] = result[column].fillna("").astype(str).str.strip()
    return result


def _require(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def build_final_verified_freeze(
    verified_before: pd.DataFrame,
    verified_additions: pd.DataFrame,
    *,
    expected_total: int = 450,
    expected_included: int | None = 217,
    expected_excluded: int | None = 233,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Merge the two frozen decision sets and validate complete final coverage."""

    required = set(DECISION_COLUMN_ORDER)
    _require(verified_before, required, "verified decisions before completion")
    _require(verified_additions, required, "verified decision additions")
    before = _clean(verified_before[DECISION_COLUMN_ORDER])
    additions = _clean(verified_additions[DECISION_COLUMN_ORDER])
    for label, frame in (("verified decisions", before), ("verified additions", additions)):
        if frame["profile_key"].duplicated().any():
            raise ValueError(f"{label} contains duplicate profile keys")
        invalid = sorted(set(frame["manual_decision"]) - ALLOWED_DECISIONS)
        if invalid:
            raise ValueError(f"{label} contains invalid decisions: {invalid}")
        incomplete = frame[FINAL_REVIEW_COLUMNS].eq("").any(axis=1)
        if incomplete.any():
            raise ValueError(
                f"{label} contains incomplete review fields for "
                f"{int(incomplete.sum())} profiles"
            )

    final = merge_verified_decisions(before, additions)
    if len(final) != expected_total:
        raise ValueError(
            f"Final verified freeze has {len(final)} profiles; expected {expected_total}"
        )
    included = int(final["manual_decision"].eq("include_dental_provider").sum())
    excluded = int(
        final["manual_decision"].eq("exclude_non_dentist_category").sum()
    )
    if expected_included is not None and included != expected_included:
        raise ValueError(
            f"Final included profile count is {included}; expected {expected_included}"
        )
    if expected_excluded is not None and excluded != expected_excluded:
        raise ValueError(
            f"Final excluded profile count is {excluded}; expected {expected_excluded}"
        )
    summary = {
        "verified_decisions_before": int(len(before)),
        "verified_additions": int(len(additions)),
        "verified_decisions_final": int(len(final)),
        "included_profiles_total": included,
        "excluded_profiles_total": excluded,
        "remaining_unresolved": 0,
    }
    return final, summary


def build_46a_compatible_decisions(
    decision_template: pd.DataFrame,
    final_verified: pd.DataFrame,
) -> pd.DataFrame:
    """Inject the nine-column verified freeze into the untouched 46a template."""

    required_template = set(IDENTITY_COLUMNS + FINAL_REVIEW_COLUMNS) | {
        "decision_id"
    }
    _require(decision_template, required_template, "stage 46a decision template")
    _require(final_verified, set(DECISION_COLUMN_ORDER), "final verified freeze")
    template = _clean(decision_template)
    verified = _clean(final_verified[DECISION_COLUMN_ORDER])
    if template["decision_id"].duplicated().any():
        raise ValueError("Stage 46a decision template contains duplicate decision IDs")
    if template["profile_key"].duplicated().any():
        raise ValueError("Stage 46a decision template contains duplicate profile keys")
    if verified["profile_key"].duplicated().any():
        raise ValueError("Final verified freeze contains duplicate profile keys")
    if set(template["profile_key"]) != set(verified["profile_key"]):
        missing = sorted(set(template["profile_key"]) - set(verified["profile_key"]))
        extra = sorted(set(verified["profile_key"]) - set(template["profile_key"]))
        raise ValueError(
            "Final verified freeze does not exactly cover the 46a template; "
            f"missing={missing[:10]}, extra={extra[:10]}"
        )

    expected = template.set_index("profile_key").sort_index()
    observed = verified.set_index("profile_key").sort_index()
    if not expected[IDENTITY_COLUMNS[0:1] + IDENTITY_COLUMNS[2:]].equals(
        observed[IDENTITY_COLUMNS[0:1] + IDENTITY_COLUMNS[2:]]
    ):
        changed = expected[
            IDENTITY_COLUMNS[0:1] + IDENTITY_COLUMNS[2:]
        ].ne(observed[IDENTITY_COLUMNS[0:1] + IDENTITY_COLUMNS[2:]]).any(axis=1)
        raise ValueError(
            "Final verified identity fields differ from the 46a template for profiles: "
            f"{expected.index[changed].tolist()[:10]}"
        )

    compatible = template.set_index("profile_key")
    compatible.loc[observed.index, FINAL_REVIEW_COLUMNS] = observed[
        FINAL_REVIEW_COLUMNS
    ]
    compatible = compatible.reset_index()[template.columns]
    if compatible[FINAL_REVIEW_COLUMNS].eq("").any(axis=None):
        raise AssertionError("46a-compatible decisions contain blank review fields")
    return compatible.sort_values("decision_id", kind="stable", ignore_index=True)


def apply_final_verified_freeze(
    inventory: pd.DataFrame,
    decision_template: pd.DataFrame,
    carry_forward_anchors: pd.DataFrame,
    verified_before: pd.DataFrame,
    verified_additions: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Build the final freeze and prepare review-only physical-location blocks."""

    final, freeze_summary = build_final_verified_freeze(
        verified_before,
        verified_additions,
    )
    compatible = build_46a_compatible_decisions(decision_template, final)
    outputs = apply_profile_decisions_and_build_location_review(
        inventory,
        decision_template,
        compatible,
        carry_forward_anchors,
    )
    reviewed, profiles, included, pairs, blocks, triage, block_profiles, location_summary = outputs
    frames = {
        "final_verified": final,
        "compatible_decisions": compatible,
        "validated_decisions": reviewed,
        "adjudicated_profiles": profiles,
        "included_outcome_profiles": included,
        "candidate_pairs": pairs,
        "review_blocks": blocks,
        "block_triage": triage,
        "block_profiles": block_profiles,
    }
    summary = {
        "analysis_status": "final_profile_eligibility_applied_location_review_prepared",
        "api_requests_submitted": 0,
        **freeze_summary,
        **location_summary,
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
        "next_required_action": (
            "Review every multi-profile physical-location block before assigning "
            "final competition location IDs. Keep outcome profiles separate."
        ),
    }
    return frames, summary
