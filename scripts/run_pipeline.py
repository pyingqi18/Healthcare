"""Plan or run a configured medical-ratings workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from medical_ratings.pipeline import (
    PipelineConfigurationError,
    PipelineExecutionError,
    load_pipeline_definition,
    plan_pipeline,
    run_pipeline,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan or execute one configuration-driven pipeline profile."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/pipeline.yaml"),
    )
    parser.add_argument(
        "--profile",
        default="corrected_v1_audit",
    )
    parser.add_argument("--from-stage")
    parser.add_argument("--to-stage")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute commands. Without this flag, only print the plan.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip a stage only when all declared outputs already exist.",
    )
    parser.add_argument(
        "--confirm-paid",
        action="append",
        default=[],
        metavar="STAGE_ID",
        help="Explicitly authorize one paid stage in this run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    try:
        definition = load_pipeline_definition(args.config)
        profile, stages = plan_pipeline(
            definition,
            args.profile,
            from_stage=args.from_stage,
            to_stage=args.to_stage,
        )
        summary = {
            "pipeline": definition.name,
            "profile": profile.name,
            "blocked": profile.blocked,
            "blocked_reason": profile.blocked_reason,
            "execution_enabled": args.run,
            "resume": args.resume,
            "stages": [
                {
                    "stage_id": stage.stage_id,
                    "description": stage.description,
                    "paid": stage.paid,
                    "ready": stage.ready,
                    "missing_inputs": list(map(str, stage.missing_inputs)),
                    "existing_outputs": list(map(str, stage.existing_outputs)),
                    "command": list(stage.command),
                }
                for stage in stages
            ],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if not args.run:
            return 0
        manifest = run_pipeline(
            definition,
            args.profile,
            from_stage=args.from_stage,
            to_stage=args.to_stage,
            resume=args.resume,
            confirmed_paid_stages=args.confirm_paid,
        )
        print(f"Run manifest: {manifest}")
        return 0
    except (PipelineConfigurationError, PipelineExecutionError) as error:
        print(f"Pipeline error: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
