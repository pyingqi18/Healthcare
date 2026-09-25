"""Tests for targeted historical-reference status adjudication."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from medical_ratings.reference_status_adjudication import (
    apply_reference_status_decisions,
    build_reference_status_decision_template,
    build_reference_status_evidence,
    parse_reference_status_results,
)


def _manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_tag": "reference_status_audit:Eureka:one",
                "market": "Eureka_CA_S",
                "reference_key": "clinic:one",
                "query": "Old Dental 1 Main St",
            },
            {
                "task_tag": "reference_status_audit:Eureka:two",
                "market": "Eureka_CA_S",
                "reference_key": "clinic:two",
                "query": "Closed Dental 2 Main St",
            },
        ]
    )


def _inventory() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market": "Eureka_CA_S",
                "reference_key": "clinic:one",
                "reference_title": "Old Dental",
                "reference_address": "1 Main St, Eureka, CA",
                "reference_zip": "95501",
                "reference_latitude": 40.8000,
                "reference_longitude": -124.1600,
                "reference_phone": "707-555-0100",
                "reference_domain": "olddental.example",
            },
            {
                "market": "Eureka_CA_S",
                "reference_key": "clinic:two",
                "reference_title": "Closed Dental",
                "reference_address": "2 Main St, Eureka, CA",
                "reference_zip": "95501",
                "reference_latitude": 40.8100,
                "reference_longitude": -124.1700,
                "reference_phone": "707-555-0200",
                "reference_domain": "closeddental.example",
            },
        ]
    )


def _task_log() -> pd.DataFrame:
    rows = []
    for index, row in _manifest().iterrows():
        rows.append(
            {
                "task_id": f"task-{index + 1}",
                "task_tag": row.task_tag,
                "market": row.market,
                "reference_key": row.reference_key,
                "query": row.query,
                "submission_status": "submitted",
            }
        )
    return pd.DataFrame(rows)


def _payload(tag: str, items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "tasks": [
            {
                "data": {"tag": tag},
                "result": [
                    {
                        "location_code": 1,
                        "language_code": "en",
                        "items": items,
                    }
                ],
            }
        ]
    }


def _write_responses(raw: Path) -> None:
    raw.mkdir()
    first = {
        "type": "maps_search",
        "rank_absolute": 1,
        "cid": "100",
        "title": "Old Dental",
        "category": "Dentist",
        "address": "1 Main St, Eureka, CA",
        "address_info": {"zip": "95501"},
        "latitude": 40.8000,
        "longitude": -124.1600,
        "phone": "707-555-0100",
        "domain": "olddental.example",
        "url": "https://example.com/old-dental",
        "business_status": "open",
        "is_closed": False,
    }
    payloads = [
        _payload(_manifest().iloc[0].task_tag, [first]),
        _payload(_manifest().iloc[1].task_tag, []),
    ]
    for index, payload in enumerate(payloads, start=1):
        (raw / f"task-{index}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


def _prepared(tmp_path: Path):
    raw = tmp_path / "raw"
    _write_responses(raw)
    observations = parse_reference_status_results(_manifest(), _task_log(), raw)
    pairs, evidence, summary = build_reference_status_evidence(
        _manifest(), _inventory(), observations
    )
    return pairs, evidence, summary


def test_parse_and_rank_reference_status_evidence(tmp_path: Path) -> None:
    pairs, evidence, summary = _prepared(tmp_path)

    assert len(pairs) == 1
    assert len(evidence) == 2
    indexed = evidence.set_index("reference_key")
    assert indexed.loc["clinic:one", "best_candidate_key"] == "google:cid:100"
    assert bool(indexed.loc["clinic:one", "best_fixed_identity_evidence"])
    assert indexed.loc["clinic:two", "returned_candidate_count"] == 0
    assert summary["automatic_status_decisions"] == 0
    assert summary["included_in_main_discovery_pipeline"] is False


def test_apply_decisions_changes_denominator_not_discovery_numerator(
    tmp_path: Path,
) -> None:
    pairs, evidence, _ = _prepared(tmp_path)
    template = build_reference_status_decision_template(evidence)
    decisions = template.copy()
    decisions.loc[decisions["reference_key"].eq("clinic:one"), [
        "manual_decision",
        "selected_candidate_key",
    ]] = ["active_same_historical_location", "google:cid:100"]
    decisions.loc[decisions["reference_key"].eq("clinic:two"), "manual_decision"] = (
        "historical_location_closed"
    )
    decisions["decision_evidence"] = "Manually reviewed saved Maps evidence"
    decisions["reviewed_by"] = "tester"
    decisions["reviewed_on"] = "2026-09-19"
    source_union = pd.DataFrame(
        [
            {
                "market": "Eureka_CA_S",
                "reference_key": "clinic:one",
                "current_reference_included_after_followup": True,
                "source_union_after_followup": False,
            },
            {
                "market": "Eureka_CA_S",
                "reference_key": "clinic:two",
                "current_reference_included_after_followup": True,
                "source_union_after_followup": False,
            },
            {
                "market": "Eureka_CA_S",
                "reference_key": "clinic:already-found",
                "current_reference_included_after_followup": True,
                "source_union_after_followup": True,
            },
        ]
    )

    _, union, by_market, summary = apply_reference_status_decisions(
        template,
        decisions,
        pairs,
        source_union,
        primary_market_minimum=0.9,
        reject_market_below=0.8,
    )

    assert summary["main_discovery_numerator_increase"] == 0
    assert summary["current_reference_units_after_status_audit"] == 2
    assert summary["source_union_units_after_status_audit"] == 1
    assert summary["targeted_status_profiles_found"] == 1
    assert union["source_union_after_status_audit"].sum() == 1
    assert by_market.loc[0, "remaining_active_reference_gaps"] == 1


def test_identity_decision_rejects_candidate_from_another_reference(
    tmp_path: Path,
) -> None:
    pairs, evidence, _ = _prepared(tmp_path)
    template = build_reference_status_decision_template(evidence)
    decisions = template.copy()
    decisions["manual_decision"] = "historical_location_closed"
    decisions["decision_evidence"] = "Manual review"
    decisions["reviewed_by"] = "tester"
    decisions["reviewed_on"] = "2026-09-19"
    decisions.loc[0, "manual_decision"] = "active_same_historical_location"
    decisions.loc[0, "selected_candidate_key"] = "google:cid:not-in-evidence"
    source_union = pd.DataFrame(
        {
            "market": ["Eureka_CA_S", "Eureka_CA_S"],
            "reference_key": ["clinic:one", "clinic:two"],
            "current_reference_included_after_followup": [True, True],
            "source_union_after_followup": [False, False],
        }
    )

    with pytest.raises(ValueError, match="outside the reference evidence"):
        apply_reference_status_decisions(
            template,
            decisions,
            pairs,
            source_union,
            primary_market_minimum=0.9,
            reject_market_below=0.8,
        )
