"""Safe, shared directory resolution for one scrape run."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Mapping


RUN_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class ScrapeRunContext:
    """Resolve raw and interim directories for one validated run name."""

    run_name: str
    raw_root: Path = Path("data/raw")
    interim_root: Path = Path("data/interim")

    def __post_init__(self) -> None:
        name = str(self.run_name).strip()
        if name in {".", ".."} or RUN_NAME_PATTERN.fullmatch(name) is None:
            raise ValueError(
                "run_name must start with a letter or number and contain only "
                "letters, numbers, dots, underscores, or hyphens"
            )
        object.__setattr__(self, "run_name", name)
        object.__setattr__(self, "raw_root", Path(self.raw_root))
        object.__setattr__(self, "interim_root", Path(self.interim_root))

    @property
    def raw_directory(self) -> Path:
        return self.raw_root / self.run_name

    @property
    def interim_directory(self) -> Path:
        return self.interim_root / self.run_name

    def path(self, scope: str, relative_path: str | Path) -> Path:
        """Return one path below the run's raw or interim directory."""

        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Run-relative paths must stay inside the run directory")
        if scope == "raw":
            return self.raw_directory / relative
        if scope == "interim":
            return self.interim_directory / relative
        raise ValueError("scope must be 'raw' or 'interim'")


def add_run_context_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the same required run name and optional roots to a CLI parser."""

    parser.add_argument(
        "--run-name",
        required=True,
        help="Stable run identifier used below data/raw and data/interim.",
    )
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--interim-root", type=Path, default=Path("data/interim")
    )


def resolve_run_context_arguments(
    args: argparse.Namespace,
    defaults: Mapping[str, tuple[str, str | Path]],
) -> argparse.Namespace:
    """Fill only omitted path arguments from the shared run context."""

    context = ScrapeRunContext(
        run_name=args.run_name,
        raw_root=args.raw_root,
        interim_root=args.interim_root,
    )
    for attribute, (scope, relative_path) in defaults.items():
        if getattr(args, attribute, None) is None:
            setattr(args, attribute, context.path(scope, relative_path))
    return args
