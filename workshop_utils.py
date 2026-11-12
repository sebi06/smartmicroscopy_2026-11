"""Shared setup for the Smart Microscopy workshop notebooks."""

import sys
from pathlib import Path


def initialize_workshop(
    example: str,
    *,
    start: Path | None = None,
    data_subdir: str = "",
) -> tuple[Path, Path, Path, Path]:
    """Find the workshop, set up example imports, and print workshop paths.

    Start from the current working directory unless a directory is supplied.
    No notebook or example files are required to identify the workshop root.
    Use the current interpreter without requiring a particular environment path.
    Return the workshop root, example directory, data directory, and model
    directory, in that order. ``data_subdir`` is relative to the data directory.
    """
    current_dir = (Path.cwd() if start is None else start).resolve()
    for candidate in (current_dir, *current_dir.parents):
        if (candidate / "pixi.toml").is_file():
            workshop_root = candidate
            break
    else:
        raise FileNotFoundError("Start from the workshop root or a subdirectory containing pixi.toml.")

    project_dir = workshop_root / "examples" / example
    data_dir = workshop_root / "data" / data_subdir
    model_dir = workshop_root / "data" / "DL_models"

    if str(project_dir) not in sys.path:
        sys.path.insert(0, str(project_dir))

    print(f"Kernel Python: {sys.executable}")
    print(f"Workshop: {workshop_root}")
    print(f"Project: {project_dir}")
    print(f"Data: {data_dir}")
    print(f"Model: {model_dir}")

    return workshop_root, project_dir, data_dir, model_dir
