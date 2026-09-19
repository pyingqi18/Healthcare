"""Tests for safe run names and shared raw/interim scrape paths."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from medical_ratings.scrape_run_context import (
    ScrapeRunContext,
    resolve_run_context_arguments,
)


RUN_SCOPED_SCRIPTS = [
    "00_plan_location_rescrape.py",
    "01_submit_location_rescrape.py",
    *[f"{index:02d}_{name}.py" for index, name in [
        (3, "check_location_result"),
        (4, "download_location_results"),
        (5, "audit_location_results"),
        (6, "parse_location_results"),
        (7, "audit_search_candidates"),
        (8, "build_clinic_candidates"),
        (9, "audit_candidate_eligibility"),
        (10, "plan_business_info_backfill"),
        (11, "submit_business_info_backfill"),
        (12, "download_business_info_results"),
        (13, "parse_business_info_results"),
        (14, "merge_business_info_candidates"),
        (15, "apply_manual_candidate_decisions"),
        (16, "audit_duplicate_candidates"),
        (17, "build_physical_location_review"),
        (18, "audit_location_resolution"),
        (19, "apply_location_resolution"),
        (20, "plan_review_collection"),
        (21, "submit_review_collection"),
        (22, "download_review_results"),
        (23, "audit_review_results"),
        (24, "parse_review_results"),
    ]],
]


def test_context_builds_separate_raw_and_interim_directories() -> None:
    context = ScrapeRunContext(
        "full_15_market_20260918",
        raw_root=Path("private/raw"),
        interim_root=Path("working/interim"),
    )

    assert context.raw_directory == Path("private/raw/full_15_market_20260918")
    assert context.interim_directory == Path(
        "working/interim/full_15_market_20260918"
    )
    assert context.path("raw", "review_results/raw") == Path(
        "private/raw/full_15_market_20260918/review_results/raw"
    )


@pytest.mark.parametrize(
    "run_name",
    ["../escape", "nested/run", "nested\\run", ".", "..", "name with spaces", ""],
)
def test_context_rejects_unsafe_run_names(run_name: str) -> None:
    with pytest.raises(ValueError, match="run_name"):
        ScrapeRunContext(run_name)


def test_default_resolution_preserves_explicit_path_override() -> None:
    args = argparse.Namespace(
        run_name="run_01",
        raw_root=Path("data/raw"),
        interim_root=Path("data/interim"),
        task_log=None,
        output=Path("custom/output.csv"),
    )

    resolved = resolve_run_context_arguments(
        args,
        {
            "task_log": ("raw", "task_log.csv"),
            "output": ("interim", "default.csv"),
        },
    )

    assert resolved.task_log == Path("data/raw/run_01/task_log.csv")
    assert resolved.output == Path("custom/output.csv")


def test_all_active_scrape_scripts_use_shared_run_context() -> None:
    scrape_directory = Path(__file__).resolve().parents[1] / "scripts" / "scrape"

    for filename in RUN_SCOPED_SCRIPTS:
        source = (scrape_directory / filename).read_text(encoding="utf-8")
        assert "add_run_context_arguments(parser)" in source, filename
        assert "rescrape_malone_syracuse_20260907" not in source, filename
