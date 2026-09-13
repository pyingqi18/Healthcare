"""Apply reviewed profile exclusions and physical-location merges."""

from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd


PROFILE_DECISIONS = {"exclude_profile", "keep_profile"}
GROUP_DECISIONS = {"merge_groups", "keep_separate"}
REQUIRED_PROFILE_COLUMNS = {
    "clinic_key",
    "cid",
    "title",
    "mapped_location",
    "physical_location_group",
    "suggested_canonical_profile",
    "profile_role",
    "votes_count",
    "observation_count",
    "address",
    "phone",
    "domain",
}
REQUIRED_ANOMALY_COLUMNS = {"clinic_key", "cid", "title"}
REQUIRED_PROFILE_DECISION_COLUMNS = {
    "clinic_key",
    "cid",
    "reviewed_title",
    "profile_decision",
    "decision_reason",
    "evidence_reference",
    "evidence_checked_at_utc",
}
REQUIRED_PAIR_COLUMNS = {"left_location_group", "right_location_group"}
REQUIRED_GROUP_DECISION_COLUMNS = {
    "left_location_group",
    "right_location_group",
    "location_decision",
    "decision_reason",
    "evidence_reference",
    "evidence_checked_at_utc",
}


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _boolean(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no", "", "nan"}:
            return False
        raise ValueError(f"Cannot interpret boolean value: {value}")
    return False if value is None or pd.isna(value) else bool(value)


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return -1.0
    return -1.0 if pd.isna(number) else number


def _pair(left: Any, right: Any) -> tuple[str, str]:
    values = sorted((_text(left), _text(right)))
    if not values[0] or not values[1]:
        raise ValueError("Location-group pair contains a blank identifier")
    if values[0] == values[1]:
        raise ValueError("Location-group pair contains the same group twice")
    return values[0], values[1]


def _location_id(keys: list[str]) -> str:
    payload = "|".join(sorted(keys))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"physical_location_final:{digest}"


def _require_columns(
    frame: pd.DataFrame,
    required: set[str],
    label: str,
) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise KeyError(f"{label} are missing columns: {sorted(missing)}")


def _require_complete_text(
    frame: pd.DataFrame,
    columns: set[str],
    label: str,
) -> None:
    for column in columns:
        values = frame[column].map(_text)
        if values.eq("").any():
            raise ValueError(f"{label} contain blank {column} values")


def _validate_profile_decisions(
    profiles: pd.DataFrame,
    anomalies: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    _require_columns(anomalies, REQUIRED_ANOMALY_COLUMNS, "Anomalies")
    _require_columns(
        decisions,
        REQUIRED_PROFILE_DECISION_COLUMNS,
        "Profile decisions",
    )
    _require_complete_text(
        decisions,
        REQUIRED_PROFILE_DECISION_COLUMNS,
        "Profile decisions",
    )
    normalized = decisions.copy()
    normalized["clinic_key"] = normalized["clinic_key"].map(_text)
    normalized["cid"] = normalized["cid"].map(_text)
    if normalized["clinic_key"].duplicated().any():
        raise ValueError("Profile decisions contain duplicate clinic_key values")
    invalid = set(normalized["profile_decision"]) - PROFILE_DECISIONS
    if invalid:
        raise ValueError(f"Invalid profile decisions: {sorted(invalid)}")

    expected = set(anomalies["clinic_key"].map(_text))
    supplied = set(normalized["clinic_key"])
    if supplied != expected:
        raise ValueError(
            "Profile-decision coverage does not match anomaly review; "
            f"missing={sorted(expected - supplied)[:5]}, "
            f"unexpected={sorted(supplied - expected)[:5]}"
        )

    identities = profiles.set_index("clinic_key")[["cid", "title"]]
    if not expected.issubset(set(identities.index)):
        raise ValueError("Anomaly review references profiles not in input")
    for row in normalized.itertuples(index=False):
        expected_cid = _text(identities.loc[row.clinic_key, "cid"])
        expected_title = _text(identities.loc[row.clinic_key, "title"])
        if row.cid != expected_cid:
            raise ValueError(f"Profile decision CID mismatch for {row.clinic_key}")
        if _text(row.reviewed_title) != expected_title:
            raise ValueError(
                f"Profile decision title mismatch for {row.clinic_key}"
            )
    return normalized


def _validate_group_decisions(
    profiles: pd.DataFrame,
    pairs: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    _require_columns(pairs, REQUIRED_PAIR_COLUMNS, "Location pairs")
    _require_columns(
        decisions,
        REQUIRED_GROUP_DECISION_COLUMNS,
        "Location decisions",
    )
    _require_complete_text(
        decisions,
        REQUIRED_GROUP_DECISION_COLUMNS,
        "Location decisions",
    )
    expected = {
        _pair(row.left_location_group, row.right_location_group)
        for row in pairs.itertuples(index=False)
    }
    normalized = decisions.copy()
    if not normalized.empty:
        normalized[["left_location_group", "right_location_group"]] = (
            pd.DataFrame(
                [
                    _pair(row.left_location_group, row.right_location_group)
                    for row in normalized.itertuples(index=False)
                ],
                index=normalized.index,
            )
        )
    supplied_pairs = list(
        zip(
            normalized["left_location_group"],
            normalized["right_location_group"],
        )
    )
    if len(set(supplied_pairs)) != len(supplied_pairs):
        raise ValueError("Location decisions contain duplicate group pairs")
    supplied = set(supplied_pairs)
    if supplied != expected:
        raise ValueError(
            "Location-decision coverage does not match pair review; "
            f"missing={sorted(expected - supplied)[:3]}, "
            f"unexpected={sorted(supplied - expected)[:3]}"
        )
    invalid = set(normalized["location_decision"]) - GROUP_DECISIONS
    if invalid:
        raise ValueError(f"Invalid location decisions: {sorted(invalid)}")
    known_groups = set(profiles["physical_location_group"].map(_text))
    referenced = set(normalized["left_location_group"]) | set(
        normalized["right_location_group"]
    )
    if not referenced.issubset(known_groups):
        raise ValueError("Location decisions reference unknown location groups")
    return normalized


def _select_canonical(group: pd.DataFrame) -> str:
    role_priority = {"organization": 2, "uncertain": 1, "individual_provider": 0}
    ranked = group.copy()
    ranked["_suggested"] = ranked["suggested_canonical_profile"].map(_boolean)
    ranked["_role"] = ranked["profile_role"].map(role_priority).fillna(0)
    ranked["_votes"] = ranked["votes_count"].map(_number)
    ranked["_observations"] = ranked["observation_count"].map(_number)
    ranked["_coverage"] = ranked.apply(
        lambda row: sum(bool(_text(row[column])) for column in ("address", "phone", "domain")),
        axis=1,
    )
    ranked = ranked.sort_values(
        ["_suggested", "_role", "_votes", "_observations", "_coverage", "clinic_key"],
        ascending=[False, False, False, False, False, True],
    )
    return _text(ranked.iloc[0]["clinic_key"])


def apply_location_resolution_decisions(
    profiles: pd.DataFrame,
    anomalies: pd.DataFrame,
    profile_decisions: pd.DataFrame,
    location_pairs: pd.DataFrame,
    location_decisions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return a complete profile crosswalk and one row per final location."""

    _require_columns(profiles, REQUIRED_PROFILE_COLUMNS, "Profiles")
    if profiles.empty:
        raise ValueError("Profiles table is empty")
    frame = profiles.copy()
    frame["clinic_key"] = frame["clinic_key"].map(_text)
    frame["cid"] = frame["cid"].map(_text)
    frame["physical_location_group"] = frame["physical_location_group"].map(_text)
    if frame["clinic_key"].eq("").any() or frame["clinic_key"].duplicated().any():
        raise ValueError("Profiles require unique nonblank clinic_key values")

    profile_rules = _validate_profile_decisions(frame, anomalies, profile_decisions)
    group_rules = _validate_group_decisions(frame, location_pairs, location_decisions)
    decision_columns = [
        "clinic_key",
        "profile_decision",
        "decision_reason",
        "evidence_reference",
        "evidence_checked_at_utc",
    ]
    crosswalk = frame.merge(
        profile_rules[decision_columns],
        on="clinic_key",
        how="left",
        validate="one_to_one",
    )
    crosswalk["final_profile_status"] = crosswalk["profile_decision"].map(
        {"exclude_profile": "excluded", "keep_profile": "included"}
    ).fillna("included")

    active = crosswalk.loc[crosswalk["final_profile_status"].eq("included")].copy()
    active_groups = set(active["physical_location_group"])
    parent = {group: group for group in active_groups}

    def find(group: str) -> str:
        while parent[group] != group:
            parent[group] = parent[parent[group]]
            group = parent[group]
        return group

    def union(left: str, right: str) -> None:
        if left not in parent or right not in parent:
            return
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            first, second = sorted((left_root, right_root))
            parent[second] = first

    merge_rules = group_rules.loc[
        group_rules["location_decision"].eq("merge_groups")
    ]
    for row in merge_rules.itertuples(index=False):
        union(row.left_location_group, row.right_location_group)

    component_groups: dict[str, set[str]] = {}
    for group in sorted(active_groups):
        component_groups.setdefault(find(group), set()).add(group)
    final_id_by_group: dict[str, str] = {}
    for groups in component_groups.values():
        keys = active.loc[
            active["physical_location_group"].isin(groups), "clinic_key"
        ].tolist()
        identifier = _location_id(keys)
        for group in groups:
            final_id_by_group[group] = identifier

    active["final_physical_location_id"] = active[
        "physical_location_group"
    ].map(final_id_by_group)
    canonical_keys: set[str] = set()
    for _, group in active.groupby("final_physical_location_id", sort=True):
        canonical_keys.add(_select_canonical(group))
    active["final_location_canonical"] = active["clinic_key"].isin(canonical_keys)

    crosswalk = crosswalk.merge(
        active[["clinic_key", "final_physical_location_id", "final_location_canonical"]],
        on="clinic_key",
        how="left",
        validate="one_to_one",
    )
    crosswalk["final_location_canonical"] = crosswalk[
        "final_location_canonical"
    ].map(lambda value: False if pd.isna(value) else _boolean(value))
    crosswalk["profile_decision"] = crosswalk["profile_decision"].fillna(
        "keep_profile_not_flagged"
    )

    active_crosswalk = crosswalk.loc[
        crosswalk["final_profile_status"].eq("included")
    ]
    counts = active_crosswalk.groupby("final_physical_location_id").agg(
        final_profile_count=("clinic_key", "size"),
        source_location_group_count=("physical_location_group", "nunique"),
    )
    locations = active_crosswalk.loc[
        active_crosswalk["final_location_canonical"]
    ].copy()
    locations = locations.merge(
        counts,
        left_on="final_physical_location_id",
        right_index=True,
        how="left",
        validate="one_to_one",
    )
    locations["absorbed_profile_count"] = locations["final_profile_count"] - 1
    if locations["final_physical_location_id"].duplicated().any():
        raise ValueError("Final locations contain duplicate identifiers")
    if len(crosswalk) != len(frame):
        raise ValueError("Profile row count changed while building crosswalk")
    if len(locations) != active_crosswalk["final_physical_location_id"].nunique():
        raise ValueError("Each final location must have exactly one canonical profile")
    return (
        crosswalk.sort_values("clinic_key").reset_index(drop=True),
        locations.sort_values(
            ["mapped_location", "final_physical_location_id"]
        ).reset_index(drop=True),
    )
