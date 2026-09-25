from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from medical_ratings.profile_eligibility_final_completion import (
    EXPECTED_PROFILE_KEYS,
    FINAL_REVIEW_COLUMNS,
    INCLUDE_SEQUENCES,
    complete_final_checkpoint,
)


def _synthetic_checkpoint() -> pd.DataFrame:
    columns = [
        "profile_key",
        "completion_sequence",
        "market",
        "title",
        "address",
        "observed_sources",
        "observed_categories",
        "source_phone",
        "source_domain",
        "official_site_url",
        "exact_google_profile_url",
        "exact_title_address_search_url",
        "organization_key",
        "evidence_route",
        *FINAL_REVIEW_COLUMNS,
    ]
    rows: list[dict[str, str]] = []
    for number in range(85):
        row = {column: "" for column in columns}
        row.update(
            {
                "profile_key": f"synthetic:decided:{number}",
                "completion_sequence": str(1000 + number),
                "market": "synthetic",
                "title": f"Prior decision {number}",
                "address": "Synthetic address",
                "exact_google_profile_url": f"https://example.test/prior/{number}",
                "manual_decision": "exclude_non_dentist_category",
                "decision_evidence": "Synthetic prior evidence",
                "evidence_url": f"https://example.test/evidence/{number}",
                "reviewed_by": "Synthetic reviewer",
                "reviewed_on": "2026-09-24",
            }
        )
        rows.append(row)
    for sequence, profile_key in EXPECTED_PROFILE_KEYS.items():
        row = {column: "" for column in columns}
        row.update(
            {
                "profile_key": profile_key,
                "completion_sequence": str(sequence),
                "market": "synthetic",
                "title": f"Synthetic profile {sequence}",
                "address": "Synthetic address",
                "observed_categories": "Synthetic category",
                "exact_google_profile_url": f"https://example.test/profile/{sequence}",
            }
        )
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def test_complete_final_checkpoint_fills_all_114_and_preserves_prior_rows() -> None:
    checkpoint = _synthetic_checkpoint()
    prior = checkpoint.iloc[:85].copy()

    completed, summary = complete_final_checkpoint(checkpoint)

    assert completed["manual_decision"].ne("").all()
    assert completed.iloc[:85].equals(prior)
    assert summary["decided_before"] == 85
    assert summary["new_decisions_added"] == 114
    assert summary["decided_after"] == 199
    assert summary["remaining_unresolved"] == 0
    newly_included = completed.loc[
        completed["completion_sequence"].astype(int).isin(EXPECTED_PROFILE_KEYS),
        "manual_decision",
    ].eq("include_dental_provider").sum()
    assert newly_included == len(INCLUDE_SEQUENCES)


def test_complete_final_checkpoint_rejects_identity_drift() -> None:
    checkpoint = _synthetic_checkpoint()
    checkpoint.loc[85, "profile_key"] = "google:cid:wrong"

    with pytest.raises(ValueError, match="identities differ"):
        complete_final_checkpoint(checkpoint)


def test_complete_final_checkpoint_requires_prior_85_decisions() -> None:
    checkpoint = _synthetic_checkpoint()
    checkpoint.loc[0, FINAL_REVIEW_COLUMNS] = ""

    with pytest.raises(ValueError, match="prior 85-decision checkpoint"):
        complete_final_checkpoint(checkpoint)


def test_cli_writes_completed_copy_and_summary_from_synthetic_input(
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "checkpoint.csv"
    output_path = tmp_path / "completed.csv"
    summary_path = tmp_path / "summary.json"
    _synthetic_checkpoint().to_csv(checkpoint_path, index=False)
    script = (
        Path(__file__).parents[1]
        / "scripts"
        / "scrape"
        / "46l_complete_all_remaining_profile_eligibility.py"
    )

    subprocess.run(
        [
            sys.executable,
            str(script),
            "--checkpoint",
            str(checkpoint_path),
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
        ],
        check=True,
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
        },
    )

    assert pd.read_csv(output_path, dtype=str, keep_default_na=False)[
        "manual_decision"
    ].ne("").all()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["remaining_unresolved"] == 0
    assert summary["new_decisions_added"] == 114
