"""Parse, deduplicate, and classify the uniform Maps core supplement."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from medical_ratings.business_listings_live import deduplicate_business_listings
from medical_ratings.parsing import parse_maps_payload


def _payload_tag(payload: Mapping[str, Any]) -> str | None:
    tasks = payload.get("tasks") or []
    if len(tasks) != 1 or not isinstance(tasks[0], Mapping):
        return None
    data = tasks[0].get("data") or {}
    return None if not isinstance(data, Mapping) or data.get("tag") is None else str(data["tag"])


def parse_saved_maps_tasks(
    task_log: pd.DataFrame,
    raw_directory: Path,
    *,
    expected_task_count: int = 30,
    expected_market_count: int = 15,
    expected_tasks_per_market: int = 2,
) -> pd.DataFrame:
    """Parse one complete, explicitly sized set of saved Maps tasks."""

    required = {"task_id", "task_tag", "market", "query", "submission_status"}
    missing = required - set(task_log.columns)
    if missing:
        raise KeyError(f"Maps task log is missing columns: {sorted(missing)}")
    submitted = task_log.loc[task_log["submission_status"].eq("submitted")].drop_duplicates("task_tag", keep="last").copy()
    if expected_task_count < 1 or expected_market_count < 1:
        raise ValueError("Expected Maps task and market counts must be positive")
    if expected_tasks_per_market < 1:
        raise ValueError("Expected Maps tasks per market must be positive")
    if (
        len(submitted) != expected_task_count
        or submitted["market"].nunique() != expected_market_count
    ):
        raise ValueError(
            "Maps parser requires all expected tasks across all expected markets"
        )
    if not submitted.groupby("market").size().eq(expected_tasks_per_market).all():
        raise ValueError("Maps parser found an incomplete per-market task set")
    records: list[dict[str, Any]] = []
    for row in submitted.to_dict(orient="records"):
        task_id = str(row["task_id"])
        task_tag = str(row["task_tag"])
        raw_path = raw_directory / f"{task_id}.json"
        if not raw_path.is_file():
            raise FileNotFoundError(f"Missing Maps raw response: {raw_path}")
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping) or _payload_tag(payload) != task_tag:
            raise ValueError(f"Maps raw response tag mismatch: {task_tag}")
        retrieved = datetime.fromtimestamp(raw_path.stat().st_mtime, timezone.utc).isoformat()
        parsed = parse_maps_payload(
            payload,
            task_id=task_id,
            query=str(row["query"]),
            requested_location=str(row["market"]),
            retrieved_at_utc=retrieved,
        )
        records.extend(parsed)
    if not records:
        raise ValueError("All saved Maps tasks returned zero observations")
    return pd.DataFrame.from_records(records)


def keyword_profile_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    """Count profiles observed by each query, including exclusive discoveries."""

    required = {"requested_location", "profile_key", "observed_queries"}
    missing = required - set(candidates.columns)
    if missing:
        raise KeyError(f"Maps candidates are missing: {sorted(missing)}")
    rows: list[dict[str, Any]] = []
    for market, group in candidates.groupby("requested_location", sort=True):
        query_sets = group["observed_queries"].map(
            lambda value: {part for part in str(value).split("|") if part}
        )
        keywords = sorted(set().union(*query_sets.tolist()))
        for keyword in keywords:
            rows.append(
                {
                    "market": market,
                    "query": keyword,
                    "profiles_observed": int(
                        query_sets.map(lambda values: keyword in values).sum()
                    ),
                    "profiles_exclusive_to_query": int(
                        query_sets.map(lambda values: values == {keyword}).sum()
                    ),
                }
            )
    return pd.DataFrame.from_records(rows)


def deduplicate_maps_by_market(observations: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate CID/place identities within each requested market."""

    cid_present = observations["cid"].astype("string").str.strip().fillna("").ne("")
    place_present = (
        observations["place_id"].astype("string").str.strip().fillna("").ne("")
    )
    organic = (
        observations["item_type"].eq("maps_search")
        if "item_type" in observations.columns
        else pd.Series(True, index=observations.index)
    )
    stable = observations.loc[organic & (cid_present | place_present)].copy()
    if stable.empty:
        raise ValueError("Maps observations contain no stable business identities")
    frames: list[pd.DataFrame] = []
    for _, group in stable.groupby("requested_location", sort=True):
        candidates = deduplicate_business_listings(group)
        query_lookup: dict[str, set[str]] = {}
        for row in group.itertuples(index=False):
            keys = []
            if pd.notna(row.cid) and str(row.cid).strip():
                keys.append(f"google:cid:{str(row.cid).strip()}")
            if pd.notna(row.place_id) and str(row.place_id).strip():
                keys.append(f"google:place_id:{str(row.place_id).strip()}")
            for key in keys:
                query_lookup.setdefault(key, set()).add(str(row.query))
        observed_queries: list[str] = []
        for row in candidates.itertuples(index=False):
            keys = []
            if pd.notna(row.cid) and str(row.cid).strip():
                keys.append(f"google:cid:{str(row.cid).strip()}")
            if pd.notna(row.place_id) and str(row.place_id).strip():
                keys.append(f"google:place_id:{str(row.place_id).strip()}")
            queries = set().union(*(query_lookup.get(key, set()) for key in keys))
            observed_queries.append("|".join(sorted(queries)))
        candidates["observed_queries"] = observed_queries
        frames.append(candidates)
    return pd.concat(frames, ignore_index=True).sort_values(
        ["requested_location", "profile_key"], ignore_index=True
    )


def _category_values(row: pd.Series) -> set[str]:
    values: set[str] = set()
    if pd.notna(row.get("category")) and str(row["category"]).strip():
        values.add(str(row["category"]).strip())
    raw = row.get("additional_categories_json")
    if pd.notna(raw) and str(raw).strip() not in {"", "null"}:
        parsed = json.loads(str(raw))
        if isinstance(parsed, list):
            for value in parsed:
                if isinstance(value, str) and value.strip():
                    values.add(value.strip())
                elif isinstance(value, Mapping):
                    label = value.get("title") or value.get("name") or value.get("category")
                    if label is not None and str(label).strip():
                        values.add(str(label).strip())
    return values


def classify_maps_categories(
    candidates: pd.DataFrame,
    category_groups: pd.DataFrame,
) -> pd.DataFrame:
    """Preserve primary and additional Google category evidence separately.

    ``legacy_category_group`` retains the earlier any-evidence priority result for
    reproducibility.  It is not a primary clinic classification.  The new
    ``primary_legacy_category_group`` and group flags make that distinction
    explicit for downstream review.
    """

    required = {"category", "legacy_category_group", "group_priority"}
    missing = required - set(category_groups.columns)
    if missing:
        raise KeyError(f"Category group map is missing columns: {sorted(missing)}")
    rules = category_groups.copy()
    rules["category_key"] = rules["category"].astype("string").str.strip().str.casefold()
    if rules["category_key"].duplicated().any():
        raise ValueError("Category group map contains duplicate categories")
    lookup = rules.set_index("category_key")[["legacy_category_group", "group_priority"]].to_dict("index")
    result = candidates.copy()
    evidence_values: list[str] = []
    mapped_values: list[str] = []
    group_values: list[str] = []
    primary_group_values: list[str] = []
    general_flags: list[bool] = []
    special_flags: list[bool] = []
    surgery_flags: list[bool] = []
    for _, row in result.iterrows():
        evidence = sorted(_category_values(row))
        matched = [lookup[value.casefold()] for value in evidence if value.casefold() in lookup]
        matched.sort(key=lambda value: int(value["group_priority"]), reverse=True)
        primary = str(row.get("category", "")).strip().casefold()
        primary_match = lookup.get(primary)
        matched_groups = {str(value["legacy_category_group"]) for value in matched}
        evidence_values.append("|".join(evidence))
        mapped_values.append("|".join(sorted(matched_groups)))
        group_values.append(str(matched[0]["legacy_category_group"]) if matched else "Unclassified")
        primary_group_values.append(
            str(primary_match["legacy_category_group"])
            if primary_match is not None
            else "Unclassified"
        )
        general_flags.append("keywords_General_Dentist" in matched_groups)
        special_flags.append("keywords_Special_Dentist" in matched_groups)
        surgery_flags.append("keywords_Surgery_Dentist" in matched_groups)
    result["google_category_evidence"] = evidence_values
    result["matched_legacy_category_groups"] = mapped_values
    result["primary_legacy_category_group"] = primary_group_values
    result["has_general_category_evidence"] = general_flags
    result["has_special_category_evidence"] = special_flags
    result["has_surgery_category_evidence"] = surgery_flags
    result["legacy_category_group_method"] = "any_evidence_highest_priority_v1"
    result["legacy_category_group"] = group_values
    return result


def keyword_overlap_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    """Count dentist-only, dental-clinic-only, and shared profiles by market."""

    records: list[dict[str, Any]] = []
    for market, group in candidates.groupby("requested_location", sort=True):
        query_sets = group["observed_queries"].map(
            lambda value: {part for part in str(value).split("|") if part}
        )
        records.append({
            "market": market,
            "unique_profiles": len(group),
            "dentist_only_profiles": int(query_sets.map(lambda value: value == {"dentist"}).sum()),
            "dental_clinic_only_profiles": int(query_sets.map(lambda value: value == {"dental clinic"}).sum()),
            "both_keywords_profiles": int(query_sets.map(lambda value: value == {"dentist", "dental clinic"}).sum()),
        })
    return pd.DataFrame.from_records(records)
