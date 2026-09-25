"""Parse and adjudicate targeted historical-reference status evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from medical_ratings.identifiers import normalize_name
from medical_ratings.parsing import parse_maps_payload


EARTH_RADIUS_METERS = 6_371_008.8
MATCH_DECISIONS = {
    "active_same_historical_location",
    "active_renamed_or_relocated_location",
}
DENOMINATOR_EXCLUSIONS = {
    "historical_location_closed",
    "historical_reference_out_of_scope",
}
ACTIVE_GAP_DECISIONS = {"active_reference_not_rediscovered"}
ALLOWED_DECISIONS = (
    MATCH_DECISIONS
    | DENOMINATOR_EXCLUSIONS
    | ACTIVE_GAP_DECISIONS
    | {"unresolved"}
)


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


def _boolean_value(value: object) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no", ""}:
        return False
    return False


def _boolean_series(values: pd.Series, label: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False).astype(bool)
    normalized = _clean(values).str.casefold()
    invalid = set(normalized.dropna()) - {"true", "false", "1", "0"}
    if invalid:
        raise ValueError(f"{label} contains invalid booleans: {sorted(invalid)}")
    return normalized.isin({"true", "1"})


def _phone(value: object) -> str | None:
    digits = re.sub(r"\D", "", _text(value))
    if not digits:
        return None
    return digits[-10:] if len(digits) >= 10 else digits


def _domain(value: object) -> str | None:
    raw = _text(value).casefold()
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").removeprefix("www.")
    return host or None


def _coordinate(value: object, lower: float, upper: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not lower <= number <= upper:
        return None
    return number


def _rank_value(value: object) -> int:
    """Return a stable sort value for an optional provider rank."""

    try:
        if value is None or pd.isna(value):
            return 10**9
        return int(value)
    except (TypeError, ValueError):
        return 10**9


def _distance_meters(reference: pd.Series, candidate: pd.Series) -> float | None:
    lat_1 = _coordinate(reference.get("reference_latitude"), -90, 90)
    lon_1 = _coordinate(reference.get("reference_longitude"), -180, 180)
    lat_2 = _coordinate(candidate.get("latitude"), -90, 90)
    lon_2 = _coordinate(candidate.get("longitude"), -180, 180)
    if None in {lat_1, lon_1, lat_2, lon_2}:
        return None
    lat_1_r, lon_1_r, lat_2_r, lon_2_r = map(
        math.radians, (lat_1, lon_1, lat_2, lon_2)
    )
    delta_latitude = lat_2_r - lat_1_r
    delta_longitude = lon_2_r - lon_1_r
    value = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(lat_1_r)
        * math.cos(lat_2_r)
        * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(min(1.0, value)))


def _similarity(left: object, right: object) -> float:
    left_value = normalize_name(left)
    right_value = normalize_name(right)
    if left_value is None or right_value is None:
        return 0.0
    return SequenceMatcher(None, left_value, right_value).ratio()


def _payload_tag(payload: Mapping[str, Any]) -> str | None:
    tasks = payload.get("tasks") or []
    if len(tasks) != 1 or not isinstance(tasks[0], Mapping):
        return None
    data = tasks[0].get("data") or {}
    if not isinstance(data, Mapping) or data.get("tag") is None:
        return None
    return str(data["tag"])


def _profile_key(row: pd.Series) -> str:
    cid = _text(row.get("cid"))
    place_id = _text(row.get("place_id"))
    if cid:
        return f"google:cid:{cid}"
    if place_id:
        return f"google:place_id:{place_id}"
    canonical = "|".join(
        _text(row.get(column)).casefold()
        for column in ("title", "address", "latitude", "longitude")
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    return f"maps_unstable:{digest}"


def parse_reference_status_results(
    manifest: pd.DataFrame,
    task_log: pd.DataFrame,
    raw_directory: Path,
) -> pd.DataFrame:
    """Parse all downloaded targeted tasks and preserve reference identity."""

    _require(
        manifest,
        {"task_tag", "market", "reference_key", "query"},
        "Reference-status manifest",
    )
    _require(
        task_log,
        {
            "task_id",
            "task_tag",
            "market",
            "reference_key",
            "query",
            "submission_status",
        },
        "Reference-status task log",
    )
    planned = manifest.copy()
    submitted = (
        task_log.loc[task_log["submission_status"].eq("submitted")]
        .drop_duplicates("task_tag", keep="last")
        .copy()
    )
    if len(submitted) != len(planned):
        raise ValueError("All reference-status tasks must be submitted before parsing")
    merged = planned.loc[:, ["task_tag", "market", "reference_key", "query"]].merge(
        submitted.loc[:, ["task_tag", "task_id", "market", "reference_key", "query"]],
        on="task_tag",
        how="left",
        validate="one_to_one",
        suffixes=("_planned", "_logged"),
    )
    for column in ("market", "reference_key", "query"):
        if not merged[f"{column}_planned"].astype(str).eq(
            merged[f"{column}_logged"].astype(str)
        ).all():
            raise ValueError(f"Task log changed planned {column}")

    records: list[dict[str, Any]] = []
    for row in merged.itertuples(index=False):
        task_id = str(row.task_id)
        task_tag = str(row.task_tag)
        raw_path = raw_directory / f"{task_id}.json"
        if not raw_path.is_file():
            raise FileNotFoundError(f"Missing reference-status response: {raw_path}")
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping) or _payload_tag(payload) != task_tag:
            raise ValueError(f"Reference-status response tag mismatch: {task_tag}")
        retrieved = datetime.fromtimestamp(
            raw_path.stat().st_mtime, timezone.utc
        ).isoformat()
        parsed = parse_maps_payload(
            payload,
            task_id=task_id,
            query=str(row.query_planned),
            requested_location=str(row.market_planned),
            retrieved_at_utc=retrieved,
        )
        for record in parsed:
            records.append(
                {
                    **record,
                    "reference_key": str(row.reference_key_planned),
                    "status_audit_task_tag": task_tag,
                }
            )
    if not records:
        columns = [
            "task_id",
            "task_tag",
            "requested_location",
            "reference_key",
            "status_audit_task_tag",
        ]
        return pd.DataFrame(columns=columns)
    return pd.DataFrame.from_records(records)


def build_reference_status_evidence(
    manifest: pd.DataFrame,
    inventory: pd.DataFrame,
    observations: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Rank candidate evidence without making historical-status decisions."""

    inventory_required = {
        "market",
        "reference_key",
        "reference_title",
        "reference_address",
        "reference_zip",
        "reference_latitude",
        "reference_longitude",
        "reference_phone",
        "reference_domain",
    }
    _require(inventory, inventory_required, "Remaining reference inventory")
    scope = manifest.loc[:, ["task_tag", "market", "reference_key", "query"]].merge(
        inventory.loc[:, sorted(inventory_required)],
        on=["market", "reference_key"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if not scope["_merge"].eq("both").all():
        raise ValueError("Audit manifest contains a reference absent from inventory")
    scope = scope.drop(columns="_merge")

    organic = observations.copy()
    if not organic.empty:
        organic = organic.loc[organic["item_type"].eq("maps_search")].copy()
        organic["candidate_key"] = organic.apply(_profile_key, axis=1)
        organic = organic.sort_values(
            ["reference_key", "source_rank", "candidate_key"],
            ignore_index=True,
        ).drop_duplicates(["reference_key", "candidate_key"], keep="first")

    pair_records: list[dict[str, Any]] = []
    reference_records: list[dict[str, Any]] = []
    for _, reference in scope.iterrows():
        if organic.empty:
            candidates = organic.copy()
        else:
            candidates = organic.loc[
                organic["reference_key"]
                .astype(str)
                .eq(str(reference["reference_key"]))
            ].copy()
        ranked: list[dict[str, Any]] = []
        for _, candidate in candidates.iterrows():
            reference_address = normalize_name(reference["reference_address"])
            candidate_address = normalize_name(candidate.get("address"))
            same_address = bool(
                reference_address is not None
                and candidate_address is not None
                and reference_address == candidate_address
            )
            reference_phone = _phone(reference["reference_phone"])
            candidate_phone = _phone(candidate.get("phone"))
            same_phone = bool(
                reference_phone
                and candidate_phone
                and reference_phone == candidate_phone
            )
            reference_domain = _domain(reference["reference_domain"])
            candidate_domain = _domain(candidate.get("domain"))
            same_domain = bool(
                reference_domain
                and candidate_domain
                and reference_domain == candidate_domain
            )
            distance = _distance_meters(reference, candidate)
            title_similarity = _similarity(
                reference["reference_title"], candidate.get("title")
            )
            within_10 = distance is not None and distance <= 10
            within_100 = distance is not None and distance <= 100
            fixed_identity_evidence = bool(
                same_address
                or (same_phone and within_100)
                or (within_10 and title_similarity >= 0.8)
            )
            status = _text(candidate.get("business_status"))
            provider_closed_signal = bool(
                _boolean_value(candidate.get("is_closed"))
                or _boolean_value(candidate.get("is_temporarily_closed"))
                or status.casefold()
                in {
                    "closed",
                    "permanently_closed",
                    "temporarily_closed",
                    "closed_temporarily",
                    "closed_permanently",
                }
            )
            record = {
                "market": reference["market"],
                "reference_key": reference["reference_key"],
                "reference_title": reference["reference_title"],
                "reference_address": reference["reference_address"],
                "candidate_key": candidate["candidate_key"],
                "candidate_title": candidate.get("title"),
                "candidate_category": candidate.get("category"),
                "candidate_address": candidate.get("address"),
                "candidate_phone": candidate.get("phone"),
                "candidate_domain": candidate.get("domain"),
                "candidate_url": candidate.get("url"),
                "candidate_business_status": candidate.get("business_status"),
                "candidate_is_closed": candidate.get("is_closed"),
                "candidate_is_temporarily_closed": candidate.get(
                    "is_temporarily_closed"
                ),
                "provider_closed_signal": provider_closed_signal,
                "source_rank": candidate.get("source_rank"),
                "distance_meters": None if distance is None else round(distance, 3),
                "same_normalized_address": same_address,
                "same_phone": same_phone,
                "same_domain": same_domain,
                "within_10_meters": within_10,
                "within_100_meters": within_100,
                "title_similarity": round(title_similarity, 4),
                "fixed_identity_evidence": fixed_identity_evidence,
                "included_in_main_discovery_pipeline": False,
            }
            ranked.append(record)
        ranked.sort(
            key=lambda row: (
                not row["fixed_identity_evidence"],
                not row["same_normalized_address"],
                not row["same_phone"],
                not row["same_domain"],
                row["distance_meters"]
                if row["distance_meters"] is not None
                else math.inf,
                -row["title_similarity"],
                _rank_value(row["source_rank"]),
                str(row["candidate_key"]),
            )
        )
        for index, record in enumerate(ranked, start=1):
            record["evidence_rank"] = index
            pair_records.append(record)
        best = ranked[0] if ranked else None
        reference_records.append(
            {
                "decision_id": f"reference_status:{reference['reference_key']}",
                "market": reference["market"],
                "reference_key": reference["reference_key"],
                "reference_title": reference["reference_title"],
                "reference_address": reference["reference_address"],
                "reference_zip": reference["reference_zip"],
                "returned_candidate_count": len(ranked),
                "fixed_identity_evidence_candidate_count": sum(
                    row["fixed_identity_evidence"] for row in ranked
                ),
                "provider_closed_signal_candidate_count": sum(
                    row["provider_closed_signal"] for row in ranked
                ),
                "best_candidate_key": "" if best is None else best["candidate_key"],
                "best_candidate_title": "" if best is None else best["candidate_title"],
                "best_candidate_category": ""
                if best is None
                else best["candidate_category"],
                "best_candidate_address": ""
                if best is None
                else best["candidate_address"],
                "best_candidate_url": "" if best is None else best["candidate_url"],
                "best_candidate_business_status": ""
                if best is None
                else best["candidate_business_status"],
                "best_candidate_provider_closed_signal": False
                if best is None
                else best["provider_closed_signal"],
                "best_distance_meters": None
                if best is None
                else best["distance_meters"],
                "best_same_address": False
                if best is None
                else best["same_normalized_address"],
                "best_same_phone": False if best is None else best["same_phone"],
                "best_same_domain": False if best is None else best["same_domain"],
                "best_title_similarity": None
                if best is None
                else best["title_similarity"],
                "best_fixed_identity_evidence": False
                if best is None
                else best["fixed_identity_evidence"],
                "included_in_main_discovery_pipeline": False,
            }
        )
    pairs = pd.DataFrame.from_records(pair_records)
    evidence = pd.DataFrame.from_records(reference_records).sort_values(
        ["market", "reference_title", "reference_key"], ignore_index=True
    )
    summary = {
        "analysis_status": "reference_status_evidence_prepared_for_manual_review",
        "api_requests_submitted": 0,
        "audit_reference_count": len(evidence),
        "references_with_any_returned_candidate": int(
            evidence["returned_candidate_count"].gt(0).sum()
        ),
        "references_with_fixed_identity_evidence": int(
            evidence["fixed_identity_evidence_candidate_count"].gt(0).sum()
        ),
        "references_with_provider_closed_signal": int(
            evidence["provider_closed_signal_candidate_count"].gt(0).sum()
        ),
        "candidate_pairs": len(pairs),
        "automatic_status_decisions": 0,
        "automatic_profile_or_location_merges": 0,
        "included_in_main_discovery_pipeline": False,
    }
    return pairs, evidence, summary


def build_reference_status_decision_template(
    evidence: pd.DataFrame,
) -> pd.DataFrame:
    """Create one editable decision row for every audited reference."""

    required = {
        "decision_id",
        "market",
        "reference_key",
        "reference_title",
        "reference_address",
        "returned_candidate_count",
        "fixed_identity_evidence_candidate_count",
        "provider_closed_signal_candidate_count",
        "best_candidate_key",
        "best_candidate_title",
        "best_candidate_address",
        "best_candidate_url",
        "best_candidate_business_status",
        "best_distance_meters",
        "best_title_similarity",
    }
    _require(evidence, required, "Reference-status evidence")
    template = evidence.copy()
    template["allowed_manual_decisions"] = "|".join(sorted(ALLOWED_DECISIONS))
    template["manual_decision"] = ""
    template["selected_candidate_key"] = ""
    template["decision_evidence"] = ""
    template["evidence_url"] = ""
    template["reviewed_by"] = ""
    template["reviewed_on"] = ""
    return template


def _validate_decisions(
    template: pd.DataFrame,
    decisions: pd.DataFrame,
    candidate_pairs: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "decision_id",
        "market",
        "reference_key",
        "reference_title",
        "manual_decision",
        "selected_candidate_key",
        "decision_evidence",
        "evidence_url",
        "reviewed_by",
        "reviewed_on",
    }
    _require(decisions, required, "Reference-status decisions")
    reviewed = decisions.copy()
    for column in required:
        reviewed[column] = _clean(reviewed[column])
    if reviewed["decision_id"].duplicated().any():
        raise ValueError("Reference-status decisions contain duplicate IDs")
    expected = template.set_index("decision_id")
    actual = reviewed.set_index("decision_id")
    if set(actual.index) != set(expected.index):
        raise ValueError("Reference-status decision IDs differ from the template")
    for column in ("market", "reference_key", "reference_title"):
        if not actual[column].eq(expected[column].astype("string").str.strip()).all():
            raise ValueError(f"Reference-status decisions changed {column}")
    candidate_lookup = (
        candidate_pairs.groupby("reference_key")["candidate_key"].agg(set).to_dict()
        if not candidate_pairs.empty
        else {}
    )
    for row in reviewed.itertuples(index=False):
        decision = _text(row.manual_decision)
        if not decision:
            raise ValueError(f"Blank manual decision for {row.decision_id}")
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"Invalid reference-status decision: {decision}")
        if not _text(row.decision_evidence):
            raise ValueError(f"Missing decision evidence for {row.decision_id}")
        if not _text(row.reviewed_by) or not _text(row.reviewed_on):
            raise ValueError(f"Missing reviewer metadata for {row.decision_id}")
        selected = _text(row.selected_candidate_key)
        if decision in MATCH_DECISIONS:
            if not selected:
                raise ValueError(
                    f"Identity decision requires a selected candidate: {row.decision_id}"
                )
            if selected not in candidate_lookup.get(str(row.reference_key), set()):
                raise ValueError(
                    f"Selected candidate is outside the reference evidence: {row.decision_id}"
                )
        elif selected:
            raise ValueError(
                f"Selected candidate is not applicable to {row.decision_id}"
            )
    return reviewed.sort_values(["market", "reference_key"], ignore_index=True)


def apply_reference_status_decisions(
    template: pd.DataFrame,
    decisions: pd.DataFrame,
    candidate_pairs: pd.DataFrame,
    source_union: pd.DataFrame,
    *,
    primary_market_minimum: float,
    reject_market_below: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Apply reviewed current-status decisions without adding targeted discovery."""

    reviewed = _validate_decisions(template, decisions, candidate_pairs)
    required = {
        "market",
        "reference_key",
        "current_reference_included_after_followup",
        "source_union_after_followup",
    }
    _require(source_union, required, "Source union after follow-up")
    union = source_union.copy()
    union["market"] = _clean(union["market"])
    union["reference_key"] = _clean(union["reference_key"])
    if union.duplicated(["market", "reference_key"]).any():
        raise ValueError("Source union contains duplicate reference keys")
    union["current_reference_included_after_status_audit"] = _boolean_series(
        union["current_reference_included_after_followup"],
        "current_reference_included_after_followup",
    )
    union["source_union_after_status_audit"] = _boolean_series(
        union["source_union_after_followup"], "source_union_after_followup"
    )
    union["reference_status_audit_decision"] = ""
    union["reference_status_selected_candidate_key"] = ""
    union["targeted_status_profile_found"] = False

    union_index = union.set_index(["market", "reference_key"]).index
    for row in reviewed.itertuples(index=False):
        key = (str(row.market), str(row.reference_key))
        if key not in union_index:
            raise ValueError(f"Audited reference is absent from source union: {key}")
        mask = union["market"].eq(row.market) & union["reference_key"].eq(
            row.reference_key
        )
        if not union.loc[mask, "current_reference_included_after_status_audit"].all():
            raise ValueError(f"Audited reference is already outside denominator: {key}")
        if union.loc[mask, "source_union_after_status_audit"].any():
            raise ValueError(f"Audited reference was already discovered: {key}")
        union.loc[mask, "reference_status_audit_decision"] = row.manual_decision
        union.loc[mask, "reference_status_selected_candidate_key"] = (
            row.selected_candidate_key
        )
        if row.manual_decision in MATCH_DECISIONS:
            union.loc[mask, "targeted_status_profile_found"] = True
        if row.manual_decision in DENOMINATOR_EXCLUSIONS:
            union.loc[mask, "current_reference_included_after_status_audit"] = False

    if not union["source_union_after_status_audit"].eq(
        _boolean_series(union["source_union_after_followup"], "source_union_after_followup")
    ).all():
        raise AssertionError("Targeted status audit changed main discovery numerator")

    market_rows: list[dict[str, Any]] = []
    for market, group in union.groupby("market", sort=True):
        current = group["current_reference_included_after_status_audit"]
        discovered = current & group["source_union_after_status_audit"]
        denominator = int(current.sum())
        found = int(discovered.sum())
        recall = found / denominator if denominator else 0.0
        if recall >= primary_market_minimum:
            next_action = "freeze_primary_discovery"
        elif recall >= reject_market_below:
            next_action = "targeted_reference_status_audit"
        else:
            next_action = "discovery_redesign_and_reference_status_audit"
        market_rows.append(
            {
                "market": market,
                "current_reference_units_after_status_audit": denominator,
                "source_union_units_after_status_audit": found,
                "source_union_recall_after_status_audit": recall,
                "remaining_active_reference_gaps": denominator - found,
                "denominator_exclusions_from_status_audit": int(
                    group["reference_status_audit_decision"]
                    .isin(DENOMINATOR_EXCLUSIONS)
                    .sum()
                ),
                "targeted_status_profiles_found": int(
                    group["targeted_status_profile_found"].sum()
                ),
                "next_action_after_status_audit": next_action,
            }
        )
    by_market = pd.DataFrame.from_records(market_rows)
    denominator = int(union["current_reference_included_after_status_audit"].sum())
    found = int(
        (
            union["current_reference_included_after_status_audit"]
            & union["source_union_after_status_audit"]
        ).sum()
    )
    unresolved = int(reviewed["manual_decision"].eq("unresolved").sum())
    summary = {
        "analysis_status": "reference_status_manual_adjudication_applied",
        "api_requests_submitted": 0,
        "reviewed_reference_status_decisions": len(reviewed),
        "decisions_by_status": {
            str(key): int(value)
            for key, value in reviewed["manual_decision"].value_counts().items()
        },
        "targeted_status_profiles_found": int(
            reviewed["manual_decision"].isin(MATCH_DECISIONS).sum()
        ),
        "current_reference_denominator_exclusions": int(
            reviewed["manual_decision"].isin(DENOMINATOR_EXCLUSIONS).sum()
        ),
        "main_discovery_numerator_increase": 0,
        "current_reference_units_after_status_audit": denominator,
        "source_union_units_after_status_audit": found,
        "source_union_recall_after_status_audit": found / denominator,
        "remaining_active_reference_gaps": denominator - found,
        "markets_by_next_action": {
            str(key): int(value)
            for key, value in by_market["next_action_after_status_audit"]
            .value_counts()
            .items()
        },
        "remaining_unresolved_status_decisions": unresolved,
        "status_adjudication_complete": unresolved == 0,
        "uniform_residual_discovery_approved": False,
        "automatic_profile_or_location_merges": 0,
        "regression_balltree_modified": False,
    }
    return reviewed, union, by_market, summary
