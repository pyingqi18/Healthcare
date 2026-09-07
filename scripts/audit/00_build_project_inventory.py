"""Create a shareable project inventory without listing data files."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
EXCLUDED_FILE_NAMES = {".env"}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "List all project directories and all files outside data folders."
        )
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/project_inventory.md"),
    )
    return parser.parse_args()


def is_excluded(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return any(part in EXCLUDED_DIRECTORY_NAMES for part in relative.parts)


def is_inside_data(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return "data" in relative.parts[:-1]


def build_inventory(root: Path) -> tuple[list[str], list[str]]:
    """Return directories and non-data files as normalized relative paths."""

    resolved_root = root.resolve()
    directories: list[str] = []
    files: list[str] = []

    for path in resolved_root.rglob("*"):
        if is_excluded(path, resolved_root):
            continue

        relative = path.relative_to(resolved_root).as_posix()
        if path.is_dir():
            directories.append(relative)
            continue

        if not path.is_file():
            continue
        if path.name in EXCLUDED_FILE_NAMES:
            continue
        if is_inside_data(path, resolved_root):
            continue
        files.append(relative)

    return (
        sorted(set(directories), key=str.casefold),
        sorted(set(files), key=str.casefold),
    )


def render_inventory(
    root: Path,
    directories: list[str],
    files: list[str],
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Project inventory",
        "",
        f"Generated at UTC: `{generated_at}`",
        f"Scanned root: `{root.resolve()}`",
        "",
        "Files located inside any `data` directory are intentionally omitted.",
        "Virtual environments, Git metadata, caches, and `.env` are omitted.",
        "",
        f"## Directories ({len(directories)})",
        "",
        *[f"* `{path}/`" for path in directories],
        "",
        f"## Files outside data ({len(files)})",
        "",
        *[f"* `{path}`" for path in files],
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    args = parse_arguments()
    directories, files = build_inventory(args.root)
    content = render_inventory(args.root, directories, files)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")

    print(f"directories: {len(directories)}")
    print(f"files_outside_data: {len(files)}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
