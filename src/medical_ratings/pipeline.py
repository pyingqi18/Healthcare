"""Configuration-driven pipeline planning and safe stage execution."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

import yaml


class PipelineConfigurationError(ValueError):
    """Raised when a pipeline configuration is incomplete or inconsistent."""


class PipelineExecutionError(RuntimeError):
    """Raised when a stage cannot be run safely or exits unsuccessfully."""


@dataclass(frozen=True)
class PipelineStage:
    """One executable pipeline stage."""

    stage_id: str
    description: str
    command: tuple[str, ...]
    inputs: tuple[Path, ...]
    outputs: tuple[Path, ...]
    depends_on: tuple[str, ...] = ()
    paid: bool = False
    confirmation_argument: str | None = None
    confirmation_value: str | None = None


@dataclass(frozen=True)
class PipelineProfile:
    """An ordered set of stages for one reproducible workflow."""

    name: str
    stage_ids: tuple[str, ...]
    blocked: bool = False
    blocked_reason: str | None = None


@dataclass(frozen=True)
class PipelineDefinition:
    """Resolved pipeline configuration."""

    name: str
    project_root: Path
    run_root: Path
    config_path: Path
    variables: Mapping[str, str]
    stages: Mapping[str, PipelineStage]
    profiles: Mapping[str, PipelineProfile]


@dataclass(frozen=True)
class PlannedStage:
    """Read-only stage status shown before execution."""

    stage_id: str
    description: str
    paid: bool
    command: tuple[str, ...]
    missing_inputs: tuple[Path, ...]
    existing_outputs: tuple[Path, ...]

    @property
    def ready(self) -> bool:
        return not self.missing_inputs


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_text(value: Any, variables: Mapping[str, str]) -> str:
    if not isinstance(value, (str, int, float)):
        raise PipelineConfigurationError(
            f"Pipeline values must be strings or numbers, found {type(value).__name__}"
        )
    try:
        return str(value).format_map(variables)
    except KeyError as exc:
        raise PipelineConfigurationError(
            f"Unknown pipeline variable: {exc.args[0]}"
        ) from exc


def _resolve_path(
    value: Any,
    *,
    project_root: Path,
    variables: Mapping[str, str],
) -> Path:
    path = Path(_resolve_text(value, variables))
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def load_pipeline_definition(path: str | Path) -> PipelineDefinition:
    """Load, resolve, and validate a pipeline YAML file."""

    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise PipelineConfigurationError(
            f"Pipeline configuration not found: {config_path}"
        )
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise PipelineConfigurationError("Pipeline YAML must contain a mapping")
    if payload.get("version") != 1:
        raise PipelineConfigurationError("Pipeline version must be 1")

    pipeline_settings = payload.get("pipeline") or {}
    if not isinstance(pipeline_settings, dict):
        raise PipelineConfigurationError("pipeline must be a mapping")
    name = str(pipeline_settings.get("name") or "medical_ratings_pipeline")

    default_root = config_path.parent.parent
    configured_root = pipeline_settings.get("project_root", str(default_root))
    project_root = Path(str(configured_root)).expanduser()
    if not project_root.is_absolute():
        project_root = (config_path.parent / project_root).resolve()
    else:
        project_root = project_root.resolve()

    raw_variables = payload.get("variables") or {}
    if not isinstance(raw_variables, dict):
        raise PipelineConfigurationError("variables must be a mapping")
    variables: dict[str, str] = {
        "python": sys.executable,
        "project_root": str(project_root),
    }
    unresolved = dict(raw_variables)
    for _ in range(len(unresolved) + 1):
        progressed = False
        for key, value in list(unresolved.items()):
            try:
                variables[str(key)] = _resolve_text(value, variables)
            except PipelineConfigurationError:
                continue
            del unresolved[key]
            progressed = True
        if not unresolved or not progressed:
            break
    if unresolved:
        raise PipelineConfigurationError(
            f"Unresolved pipeline variables: {sorted(map(str, unresolved))}"
        )

    run_root = _resolve_path(
        pipeline_settings.get("run_root", "outputs/pipeline_runs"),
        project_root=project_root,
        variables=variables,
    )

    raw_stages = payload.get("stages") or {}
    if not isinstance(raw_stages, dict):
        raise PipelineConfigurationError("stages must be a mapping")
    stages: dict[str, PipelineStage] = {}
    for raw_id, raw_stage in raw_stages.items():
        stage_id = str(raw_id)
        if not isinstance(raw_stage, dict):
            raise PipelineConfigurationError(
                f"Stage {stage_id} must be a mapping"
            )
        raw_command = raw_stage.get("command")
        if not isinstance(raw_command, list) or not raw_command:
            raise PipelineConfigurationError(
                f"Stage {stage_id} command must be a non-empty list"
            )
        command = tuple(_resolve_text(item, variables) for item in raw_command)
        inputs = tuple(
            _resolve_path(
                item,
                project_root=project_root,
                variables=variables,
            )
            for item in raw_stage.get("inputs", [])
        )
        outputs = tuple(
            _resolve_path(
                item,
                project_root=project_root,
                variables=variables,
            )
            for item in raw_stage.get("outputs", [])
        )
        paid = bool(raw_stage.get("paid", False))
        confirmation_argument = raw_stage.get("confirmation_argument")
        confirmation_value = raw_stage.get("confirmation_value")
        if paid and (not confirmation_argument or not confirmation_value):
            raise PipelineConfigurationError(
                f"Paid stage {stage_id} requires confirmation_argument and confirmation_value"
            )
        stages[stage_id] = PipelineStage(
            stage_id=stage_id,
            description=str(raw_stage.get("description") or stage_id),
            command=command,
            inputs=inputs,
            outputs=outputs,
            depends_on=tuple(map(str, raw_stage.get("depends_on", []))),
            paid=paid,
            confirmation_argument=(
                None if confirmation_argument is None else str(confirmation_argument)
            ),
            confirmation_value=(
                None if confirmation_value is None else str(confirmation_value)
            ),
        )

    raw_profiles = payload.get("profiles") or {}
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise PipelineConfigurationError("profiles must be a non-empty mapping")
    profiles: dict[str, PipelineProfile] = {}
    for raw_name, raw_profile in raw_profiles.items():
        profile_name = str(raw_name)
        if not isinstance(raw_profile, dict):
            raise PipelineConfigurationError(
                f"Profile {profile_name} must be a mapping"
            )
        stage_ids = tuple(map(str, raw_profile.get("stages", [])))
        blocked = bool(raw_profile.get("blocked", False))
        blocked_reason = raw_profile.get("blocked_reason")
        if not stage_ids and not blocked:
            raise PipelineConfigurationError(
                f"Profile {profile_name} must include at least one stage"
            )
        unknown = [stage_id for stage_id in stage_ids if stage_id not in stages]
        if unknown:
            raise PipelineConfigurationError(
                f"Profile {profile_name} references unknown stages: {unknown}"
            )
        position = {stage_id: index for index, stage_id in enumerate(stage_ids)}
        for stage_id in stage_ids:
            for dependency in stages[stage_id].depends_on:
                if dependency not in position:
                    raise PipelineConfigurationError(
                        f"Profile {profile_name} omits dependency {dependency} for {stage_id}"
                    )
                if position[dependency] >= position[stage_id]:
                    raise PipelineConfigurationError(
                        f"Profile {profile_name} must place {dependency} before {stage_id}"
                    )
        profiles[profile_name] = PipelineProfile(
            name=profile_name,
            stage_ids=stage_ids,
            blocked=blocked,
            blocked_reason=None if blocked_reason is None else str(blocked_reason),
        )

    return PipelineDefinition(
        name=name,
        project_root=project_root,
        run_root=run_root,
        config_path=config_path,
        variables=variables,
        stages=stages,
        profiles=profiles,
    )


def select_stage_ids(
    profile: PipelineProfile,
    *,
    from_stage: str | None = None,
    to_stage: str | None = None,
) -> tuple[str, ...]:
    """Return one contiguous stage selection from an ordered profile."""

    stage_ids = profile.stage_ids
    if not stage_ids:
        return ()
    start = 0
    stop = len(stage_ids)
    if from_stage is not None:
        if from_stage not in stage_ids:
            raise PipelineConfigurationError(
                f"Unknown --from-stage for profile {profile.name}: {from_stage}"
            )
        start = stage_ids.index(from_stage)
    if to_stage is not None:
        if to_stage not in stage_ids:
            raise PipelineConfigurationError(
                f"Unknown --to-stage for profile {profile.name}: {to_stage}"
            )
        stop = stage_ids.index(to_stage) + 1
    if start >= stop:
        raise PipelineConfigurationError(
            "--from-stage must not appear after --to-stage"
        )
    return stage_ids[start:stop]


def plan_pipeline(
    definition: PipelineDefinition,
    profile_name: str,
    *,
    from_stage: str | None = None,
    to_stage: str | None = None,
) -> tuple[PipelineProfile, tuple[PlannedStage, ...]]:
    """Inspect stage readiness without executing commands."""

    if profile_name not in definition.profiles:
        raise PipelineConfigurationError(f"Unknown pipeline profile: {profile_name}")
    profile = definition.profiles[profile_name]
    selected = select_stage_ids(
        profile,
        from_stage=from_stage,
        to_stage=to_stage,
    )
    planned: list[PlannedStage] = []
    outputs_from_earlier_stages: set[Path] = set()
    for stage_id in selected:
        stage = definition.stages[stage_id]
        planned.append(
            PlannedStage(
                stage_id=stage_id,
                description=stage.description,
                paid=stage.paid,
                command=stage.command,
                missing_inputs=tuple(
                    path
                    for path in stage.inputs
                    if not path.exists() and path not in outputs_from_earlier_stages
                ),
                existing_outputs=tuple(path for path in stage.outputs if path.exists()),
            )
        )
        outputs_from_earlier_stages.update(stage.outputs)
    return profile, tuple(planned)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint_path(path: Path) -> dict[str, Any]:
    """Return a stable provenance record for one file or directory."""

    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    record: dict[str, Any] = {
        "path": str(path),
        "exists": True,
        "kind": "directory" if path.is_dir() else "file",
        "size_bytes": stat.st_size,
        "modified_at_ns": stat.st_mtime_ns,
    }
    if path.is_file():
        record["sha256"] = _sha256(path)
    return record


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _display_command(stage: PipelineStage, command: Sequence[str]) -> list[str]:
    displayed = list(command)
    if stage.paid and stage.confirmation_value:
        displayed = [
            "<PAID_CONFIRMATION>" if item == stage.confirmation_value else item
            for item in displayed
        ]
    return displayed


def run_pipeline(
    definition: PipelineDefinition,
    profile_name: str,
    *,
    from_stage: str | None = None,
    to_stage: str | None = None,
    resume: bool = False,
    confirmed_paid_stages: Sequence[str] = (),
) -> Path:
    """Execute selected stages and return the run-manifest path."""

    profile, planned = plan_pipeline(
        definition,
        profile_name,
        from_stage=from_stage,
        to_stage=to_stage,
    )
    if profile.blocked:
        reason = profile.blocked_reason or "No blocked_reason was recorded"
        raise PipelineExecutionError(
            f"Pipeline profile {profile_name} is blocked: {reason}"
        )

    confirmed = set(confirmed_paid_stages)
    selected_ids = {item.stage_id for item in planned}
    unknown_confirmations = confirmed - selected_ids
    if unknown_confirmations:
        raise PipelineExecutionError(
            "Paid confirmation supplied for stages outside this run: "
            f"{sorted(unknown_confirmations)}"
        )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    run_directory = definition.run_root / run_id
    manifest_path = run_directory / "run_manifest.json"
    manifest: dict[str, Any] = {
        "pipeline_name": definition.name,
        "profile": profile_name,
        "run_id": run_id,
        "status": "running",
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "project_root": str(definition.project_root),
        "config": fingerprint_path(definition.config_path),
        "from_stage": from_stage,
        "to_stage": to_stage,
        "resume": resume,
        "stages": [],
    }
    _write_json_atomic(manifest_path, manifest)

    for item in planned:
        stage = definition.stages[item.stage_id]
        stage_record: dict[str, Any] = {
            "stage_id": stage.stage_id,
            "description": stage.description,
            "paid": stage.paid,
            "status": "pending",
            "started_at_utc": None,
            "finished_at_utc": None,
            "command": list(stage.command),
            "inputs": [fingerprint_path(path) for path in stage.inputs],
            "outputs": [fingerprint_path(path) for path in stage.outputs],
        }
        manifest["stages"].append(stage_record)

        if resume and stage.outputs and all(path.exists() for path in stage.outputs):
            stage_record["status"] = "skipped_existing_outputs"
            stage_record["finished_at_utc"] = _utc_now()
            _write_json_atomic(manifest_path, manifest)
            continue

        missing_inputs = [path for path in stage.inputs if not path.exists()]
        if missing_inputs:
            stage_record["status"] = "blocked_missing_inputs"
            stage_record["finished_at_utc"] = _utc_now()
            manifest["status"] = "failed"
            manifest["finished_at_utc"] = _utc_now()
            _write_json_atomic(manifest_path, manifest)
            raise PipelineExecutionError(
                f"Stage {stage.stage_id} is missing inputs: "
                + ", ".join(map(str, missing_inputs))
            )

        command = list(stage.command)
        if stage.paid:
            if stage.stage_id not in confirmed:
                stage_record["status"] = "blocked_paid_confirmation"
                stage_record["finished_at_utc"] = _utc_now()
                manifest["status"] = "failed"
                manifest["finished_at_utc"] = _utc_now()
                _write_json_atomic(manifest_path, manifest)
                raise PipelineExecutionError(
                    f"Paid stage {stage.stage_id} requires "
                    f"--confirm-paid {stage.stage_id}"
                )
            command.extend(
                [str(stage.confirmation_argument), str(stage.confirmation_value)]
            )

        stage_record["command"] = _display_command(stage, command)
        stage_record["status"] = "running"
        stage_record["started_at_utc"] = _utc_now()
        _write_json_atomic(manifest_path, manifest)
        completed = subprocess.run(
            command,
            cwd=definition.project_root,
            check=False,
        )
        stage_record["return_code"] = completed.returncode
        stage_record["finished_at_utc"] = _utc_now()
        if completed.returncode != 0:
            stage_record["status"] = "failed_command"
            manifest["status"] = "failed"
            manifest["finished_at_utc"] = _utc_now()
            _write_json_atomic(manifest_path, manifest)
            raise PipelineExecutionError(
                f"Stage {stage.stage_id} exited with code {completed.returncode}"
            )

        missing_outputs = [path for path in stage.outputs if not path.exists()]
        stage_record["outputs"] = [
            fingerprint_path(path) for path in stage.outputs
        ]
        if missing_outputs:
            stage_record["status"] = "failed_missing_outputs"
            manifest["status"] = "failed"
            manifest["finished_at_utc"] = _utc_now()
            _write_json_atomic(manifest_path, manifest)
            raise PipelineExecutionError(
                f"Stage {stage.stage_id} did not create outputs: "
                + ", ".join(map(str, missing_outputs))
            )
        stage_record["status"] = "completed"
        _write_json_atomic(manifest_path, manifest)

    manifest["status"] = "completed"
    manifest["finished_at_utc"] = _utc_now()
    _write_json_atomic(manifest_path, manifest)
    return manifest_path
