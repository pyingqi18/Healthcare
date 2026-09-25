from __future__ import annotations

import pandas as pd
import pytest

from medical_ratings.profile_eligibility_final_application import (
    build_46a_compatible_decisions,
    build_final_verified_freeze,
)


def _decision(profile_key: str, decision: str) -> dict[str, str]:
    number = profile_key.rsplit(":", 1)[-1]
    return {
        "market": "Market",
        "profile_key": profile_key,
        "title": f"Clinic {number}",
        "address": f"{number} Main St",
        "manual_decision": decision,
        "decision_evidence": f"Evidence {number}",
        "evidence_url": f"https://example.test/{number}",
        "reviewed_by": "reviewer",
        "reviewed_on": "2026-09-25",
    }


def _verified_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    before = pd.DataFrame(
        [
            _decision("google:cid:1", "include_dental_provider"),
            _decision("google:cid:2", "exclude_non_dentist_category"),
        ]
    )
    additions = pd.DataFrame(
        [_decision("google:cid:3", "include_dental_provider")]
    )
    return before, additions


def _template() -> pd.DataFrame:
    rows = []
    for number in (1, 2, 3):
        rows.append(
            {
                "decision_id": f"profile:Market:google:cid:{number}",
                "market": "Market",
                "profile_key": f"google:cid:{number}",
                "title": f"Clinic {number}",
                "address": f"{number} Main St",
                "observed_sources": "maps_core",
                "observed_categories": "Dentist",
                "allowed_manual_decisions": (
                    "exclude_non_dentist_category|include_dental_provider"
                ),
                "manual_decision": "",
                "decision_evidence": "",
                "evidence_url": "",
                "reviewed_by": "",
                "reviewed_on": "",
            }
        )
    return pd.DataFrame(rows)


def test_build_final_verified_freeze_merges_complete_disjoint_inputs() -> None:
    before, additions = _verified_inputs()

    final, summary = build_final_verified_freeze(
        before,
        additions,
        expected_total=3,
        expected_included=2,
        expected_excluded=1,
    )

    assert len(final) == 3
    assert summary["verified_decisions_final"] == 3
    assert summary["remaining_unresolved"] == 0


def test_build_final_verified_freeze_rejects_incomplete_review_fields() -> None:
    before, additions = _verified_inputs()
    additions.loc[0, "evidence_url"] = ""

    with pytest.raises(ValueError, match="incomplete review fields"):
        build_final_verified_freeze(
            before,
            additions,
            expected_total=3,
            expected_included=2,
            expected_excluded=1,
        )


def test_build_46a_compatible_decisions_preserves_template_and_adds_reviews() -> None:
    before, additions = _verified_inputs()
    final, _ = build_final_verified_freeze(
        before,
        additions,
        expected_total=3,
        expected_included=2,
        expected_excluded=1,
    )

    compatible = build_46a_compatible_decisions(_template(), final)

    assert list(compatible.columns) == list(_template().columns)
    assert compatible["manual_decision"].ne("").all()
    assert compatible["observed_sources"].eq("maps_core").all()
    assert compatible["profile_key"].nunique() == 3


def test_build_46a_compatible_decisions_rejects_identity_drift() -> None:
    before, additions = _verified_inputs()
    final, _ = build_final_verified_freeze(
        before,
        additions,
        expected_total=3,
        expected_included=2,
        expected_excluded=1,
    )
    final.loc[final["profile_key"].eq("google:cid:3"), "address"] = "Changed"

    with pytest.raises(ValueError, match="identity fields differ"):
        build_46a_compatible_decisions(_template(), final)
