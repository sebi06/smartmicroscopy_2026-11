r"""Create a reference-backed CZI archive without importing a GUI.

Run in a terminal from the workshop root (the folder containing pixi.toml)::

    pixi install --locked
    pixi run --locked python examples\czi_handling\create_czi_vzip.py --help
    pixi run --locked python examples\czi_handling\create_czi_vzip.py "data\RatBrain_Z79_ZSTD.czi"
    pixi run --locked python examples\czi_handling\create_czi_vzip.py "data\RatBrain_Z79_ZSTD.czi" -o "data\RatBrain_Z79_ZSTD.vzip"
    pixi run --locked python examples\czi_handling\create_czi_vzip.py "data\RatBrain_Z79_ZSTD.czi" -o "data\RatBrain_Z79_ZSTD.vzip" --overwrite

``pixi run`` selects and activates this workshop's default environment even
when the terminal prompt shows Conda ``(base)``. Selecting a Python interpreter
in VS Code does not activate it in an existing terminal. The workshop manifest
includes czitools[all], which supplies the VZIP dependencies; no separate pip
install is needed.

Alternatively, run ``pixi shell`` from the workshop root, then use the same
Python commands without the ``pixi run --locked`` prefix. Exit that shell with
``exit``.

Input and output paths are relative to the terminal's current directory.
Quote paths containing spaces. Without -o, the archive is saved beside the CZI.
The destination directory must already exist, and --overwrite explicitly
allows replacing an existing archive. The archive references, rather than
copies, the pixel data: keep the original CZI unchanged at its referenced
location. The archive is not a standalone copy of the image.
"""

import argparse
import sys
from pathlib import Path

from czitools.export_tools import create_czi_vzip

# Make the shared utility importable from any workshop subdirectory.
for utility_dir in (Path.cwd().resolve(), *Path.cwd().resolve().parents):
    if (utility_dir / "workshop_utils.py").is_file():
        if str(utility_dir) not in sys.path:
            sys.path.insert(0, str(utility_dir))
        break
else:
    raise FileNotFoundError("Start from the workshop root or a subdirectory.")

from workshop_utils import initialize_workshop

workshop_root, project_dir, data_dir, model_dir = initialize_workshop("czi_handling")


def main(argv: list[str] | None = None) -> int:
    """Export one CZI using the same API a future napari worker can call.

    Args:
        argv (list[str] | None): Arguments, or None for command-line arguments.

    Returns:
        int: Zero after a successful export.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Existing local .czi file")
    parser.add_argument("-o", "--output", type=Path, help="Destination .vzip (default: beside the CZI)")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing archive")
    args = parser.parse_args(argv)
    try:
        archive = create_czi_vzip(args.source, args.output, overwrite=args.overwrite)
    except (OSError, ValueError, ImportError) as error:
        parser.exit(2, f"Export failed: {error}\n")
    print(f"Saved: {archive}")
    print("Keep the original CZI unchanged at its referenced location.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
