"""Tests for pipeline configuration, planning, safety gates, and resumption."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from medical_ratings.pipeline import (
    PipelineExecutionError,
    load_pipeline_definition,
    plan_pipeline,
    run_pipeline,
    select_stage_ids,
)


def write_config(path: Path, project_root: Path) -> None:
    path.write_text(
        f"""
version: 1
pipeline:
  name: test_pipeline
  project_root: {project_root.as_posix()}
  run_root: runs
variables:
  input: input.txt
  first_output: first.txt
  paid_output: paid.txt
profiles:
  normal:
    stages: [first, paid]
  blocked:
    blocked: true
    blocked_reason: batch-specific code remains
    stages: []
stages:
  first:
    description: first stage
    command:
      - "{{python}}"
      - -c
      - "from pathlib import Path; Path('first.txt').write_text('first')"
    inputs: ["{{input}}"]
    outputs: ["{{first_output}}"]
  paid:
    description: paid stage
    depends_on: [first]
    paid: true
    confirmation_argument: --confirmation
    confirmation_value: EXACT_CONFIRMATION
    command:
      - "{{python}}"
      - -c
      - "import sys; from pathlib import Path; assert sys.argv[1:] == ['--confirmation', 'EXACT_CONFIRMATION']; Path('paid.txt').write_text('paid')"
    inputs: ["{{first_output}}"]
    outputs: ["{{paid_output}}"]
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_project_pipeline_configuration_resolves_order() -> None:
    definition = load_pipeline_definition(Path("config/pipeline.yaml"))
    profile = definition.profiles["corrected_v1_audit"]

    assert profile.stage_ids[0] == "regression_readiness"
    assert profile.stage_ids[-1] == "strict_spatial_suite"
    assert select_stage_ids(
        profile,
        from_stage="strict_self_exclusion",
        to_stage="strict_market_year_effects",
    ) == (
        "strict_self_exclusion",
        "strict_year_effects",
        "strict_market_year_effects",
    )


def test_plan_reports_missing_inputs_without_running(tmp_path: Path) -> None:
    config = tmp_path / "pipeline.yaml"
    write_config(config, tmp_path)
    definition = load_pipeline_definition(config)

    _, planned = plan_pipeline(definition, "normal", to_stage="first")

    assert planned[0].ready is False
    assert planned[0].missing_inputs == (tmp_path / "input.txt",)
    assert not (tmp_path / "first.txt").exists()


def test_plan_treats_upstream_outputs_as_available_to_downstream(tmp_path: Path) -> None:
    config = tmp_path / "pipeline.yaml"
    write_config(config, tmp_path)
    (tmp_path / "input.txt").write_text("input", encoding="utf-8")
    definition = load_pipeline_definition(config)

    _, planned = plan_pipeline(definition, "normal")

    assert [stage.ready for stage in planned] == [True, True]
    assert not (tmp_path / "first.txt").exists()


def test_run_requires_paid_stage_confirmation(tmp_path: Path) -> None:
    config = tmp_path / "pipeline.yaml"
    write_config(config, tmp_path)
    (tmp_path / "input.txt").write_text("input", encoding="utf-8")
    definition = load_pipeline_definition(config)

    with pytest.raises(PipelineExecutionError, match="--confirm-paid paid"):
        run_pipeline(definition, "normal")

    assert (tmp_path / "first.txt").read_text(encoding="utf-8") == "first"
    assert not (tmp_path / "paid.txt").exists()


def test_confirmed_paid_stage_runs_and_redacts_manifest(tmp_path: Path) -> None:
    config = tmp_path / "pipeline.yaml"
    write_config(config, tmp_path)
    (tmp_path / "input.txt").write_text("input", encoding="utf-8")
    definition = load_pipeline_definition(config)

    manifest_path = run_pipeline(
        definition,
        "normal",
        confirmed_paid_stages=["paid"],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["status"] == "completed"
    assert (tmp_path / "paid.txt").read_text(encoding="utf-8") == "paid"
    paid = manifest["stages"][1]
    assert paid["status"] == "completed"
    assert "EXACT_CONFIRMATION" not in paid["command"]
    assert "<PAID_CONFIRMATION>" in paid["command"]
    assert paid["outputs"][0]["sha256"]


def test_resume_skips_existing_outputs(tmp_path: Path) -> None:
    config = tmp_path / "pipeline.yaml"
    write_config(config, tmp_path)
    (tmp_path / "input.txt").write_text("input", encoding="utf-8")
    (tmp_path / "first.txt").write_text("existing", encoding="utf-8")
    definition = load_pipeline_definition(config)

    manifest_path = run_pipeline(
        definition,
        "normal",
        to_stage="first",
        resume=True,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["stages"][0]["status"] == "skipped_existing_outputs"
    assert (tmp_path / "first.txt").read_text(encoding="utf-8") == "existing"


def test_blocked_full_rebuild_cannot_run(tmp_path: Path) -> None:
    config = tmp_path / "pipeline.yaml"
    write_config(config, tmp_path)
    definition = load_pipeline_definition(config)

    with pytest.raises(PipelineExecutionError, match="batch-specific code remains"):
        run_pipeline(definition, "blocked")
