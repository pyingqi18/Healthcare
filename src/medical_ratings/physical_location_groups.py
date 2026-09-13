"""Group Google profiles into reviewable physical dental locations."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pandas as pd


REQUIRED_CANDIDATE_COLUMNS = {
    "clinic_key",
    "cid",
    "title",
    "mapped_location",
    "votes_count",
    "observation_count",
    "address",
    "phone",
    "domain",
    "final_included",
}
REQUIRED_PAIR_COLUMNS = {
    "left_clinic_key",
    "right_clinic_key",
    "same_phone",
    "same_domain",
    "same_address",
    "within_50_meters",
    "title_similarity",
}
INDIVIDUAL_PATTERN = re.compile(r"(?:^|\W)(?:dr|dds|dmd|bds)(?:\W|$)", re.I)
ORGANIZATION_PATTERN = re.compile(
    r"\b(?:dental|dentistry|clinic|center|orthodontic|orthodontics|"
    r"periodontics|endodontics|prosthodontics|associates|practice|group|"
    r"smiles)\b|oral\b.*\bsurgery\b",
    re.I,
)
CORPORATE_SUFFIX_PATTERN = re.compile(r"(?:\bpllc\b|\bp\.?c\.?)\s*$", re.I)


def _boolean(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no", "", "nan"}:
            return False
        raise ValueError(f"Cannot interpret boolean value: {value}")
    if value is None or pd.isna(value):
        return False
    return bool(value)


def _profile_role(title: Any) -> str:
    text = "" if title is None or pd.isna(title) else str(title).strip()
    if CORPORATE_SUFFIX_PATTERN.search(text):
        return "organization"
    if INDIVIDUAL_PATTERN.search(text):
        return "individual_provider"
    if ORGANIZATION_PATTERN.search(text):
        return "organization"
    return "uncertain"


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return -1.0
    return -1.0 if pd.isna(number) else number


def _has_value(value: Any) -> bool:
    return value is not None and not pd.isna(value) and bool(str(value).strip())


def _group_id(keys: list[str]) -> str:
    payload = "|".join(sorted(keys))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"physical_location:{digest}"


def _is_location_edge(row: pd.Series) -> bool:
    same_phone = _boolean(row["same_phone"])
    same_domain = _boolean(row["same_domain"])
    same_address = _boolean(row["same_address"])
    within_50 = _boolean(row["within_50_meters"])
    similarity = _number(row["title_similarity"])
    return (
        (same_address and (same_phone or same_domain))
        or (within_50 and (same_phone or same_domain))
        or (within_50 and similarity >= 0.90)
    )


def build_physical_location_review(
    candidates: pd.DataFrame,
    pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Return included profiles with deterministic location-group suggestions."""

    missing_candidates = REQUIRED_CANDIDATE_COLUMNS - set(candidates.columns)
    if missing_candidates:
        raise KeyError(
            f"Candidates are missing columns: {sorted(missing_candidates)}"
        )
    missing_pairs = REQUIRED_PAIR_COLUMNS - set(pairs.columns)
    if missing_pairs:
        raise KeyError(f"Pairs are missing columns: {sorted(missing_pairs)}")
    if candidates.empty:
        raise ValueError("Candidates table is empty")
    if candidates["clinic_key"].isna().any():
        raise ValueError("Candidates contain missing clinic_key values")
    if candidates["clinic_key"].duplicated().any():
        raise ValueError("Candidates contain duplicate clinic_key values")

    included_mask = candidates["final_included"].map(_boolean)
    included = candidates.loc[included_mask].copy()
    included["clinic_key"] = included["clinic_key"].astype("string").str.strip()
    included_keys = set(included["clinic_key"])

    pair_frame = pairs.copy()
    pair_frame["left_clinic_key"] = (
        pair_frame["left_clinic_key"].astype("string").str.strip()
    )
    pair_frame["right_clinic_key"] = (
        pair_frame["right_clinic_key"].astype("string").str.strip()
    )
    referenced_keys = set(pair_frame["left_clinic_key"]) | set(
        pair_frame["right_clinic_key"]
    )
    unexpected = sorted(referenced_keys - included_keys)
    if unexpected:
        raise ValueError(
            "Duplicate pairs reference non-included candidates: "
            f"{unexpected[:5]}"
        )
    if (pair_frame["left_clinic_key"] == pair_frame["right_clinic_key"]).any():
        raise ValueError("Duplicate pairs contain a self-pair")

    parent = {key: key for key in included_keys}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        first, second = sorted((left_root, right_root))
        parent[second] = first

    location_edges = pair_frame.loc[pair_frame.apply(_is_location_edge, axis=1)]
    for row in location_edges.itertuples(index=False):
        union(str(row.left_clinic_key), str(row.right_clinic_key))

    components: dict[str, list[str]] = {}
    for key in sorted(included_keys):
        components.setdefault(find(key), []).append(key)

    group_for_key: dict[str, str] = {}
    group_size: dict[str, int] = {}
    for keys in components.values():
        identifier = _group_id(keys)
        for key in keys:
            group_for_key[key] = identifier
            group_size[key] = len(keys)

    included["physical_location_group"] = included["clinic_key"].map(
        group_for_key
    )
    included["location_group_size"] = included["clinic_key"].map(group_size)
    included["profile_role"] = included["title"].map(_profile_role)

    canonical_keys: set[str] = set()
    canonical_reasons: dict[str, str] = {}
    role_priority = {"organization": 1, "uncertain": 0, "individual_provider": 0}
    for _, group in included.groupby("physical_location_group", sort=True):
        ranked = group.copy()
        ranked["_role_score"] = ranked["profile_role"].map(role_priority)
        ranked["_votes_score"] = ranked["votes_count"].map(_number)
        ranked["_observation_score"] = ranked["observation_count"].map(_number)
        ranked["_completeness"] = ranked.apply(
            lambda row: sum(
                _has_value(row[column])
                for column in ("address", "phone", "domain")
            ),
            axis=1,
        )
        ranked = ranked.sort_values(
            [
                "_role_score",
                "_votes_score",
                "_observation_score",
                "_completeness",
                "clinic_key",
            ],
            ascending=[False, False, False, False, True],
        )
        selected = str(ranked.iloc[0]["clinic_key"])
        canonical_keys.add(selected)
        role = str(ranked.iloc[0]["profile_role"])
        canonical_reasons[selected] = (
            f"preferred {role} profile, then highest review count and coverage"
        )

    included["suggested_canonical_profile"] = included["clinic_key"].isin(
        canonical_keys
    )
    included["canonical_suggestion_reason"] = included["clinic_key"].map(
        canonical_reasons
    )
    included["location_review_status"] = included["location_group_size"].map(
        lambda size: "singleton_no_review_needed"
        if size == 1
        else "pending_location_group_review"
    )
    return included.sort_values(
        [
            "mapped_location",
            "physical_location_group",
            "suggested_canonical_profile",
            "title",
        ],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)
