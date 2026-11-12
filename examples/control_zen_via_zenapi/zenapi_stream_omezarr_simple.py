"""Run experiment-driven OME-Zarr streaming with optional post-processing.

Set ``PYRAMID_LEVELS`` to:
    - 0 to disable post-acquisition pyramid creation.
    - 1 to create a 2x Y/X level.
    - 2 to create 2x and 4x Y/X levels.
    - 3 to create 2x, 4x, and 8x Y/X levels.

Level 0 is written and sharded during acquisition. Pyramid generation runs
after acquisition and writes only levels 1..N. Set
``SPATIAL_SHARD_SIZE_CHUNKS`` to ``None`` to disable sharding for all levels.
"""

import asyncio
import os
import sys
from pathlib import Path

from zenapi_stream2omezarr_experiment import stream_experiment

# Direct interpreter launches do not apply Pixi's native-library PATH activation.
native_dll_dir = Path(sys.prefix) / "Library" / "bin"
if os.name == "nt" and native_dll_dir.is_dir():
    os.environ["PATH"] = str(native_dll_dir) + os.pathsep + os.environ.get("PATH", "")

# Make the shared utility importable from any workshop subdirectory.
for utility_dir in (Path.cwd().resolve(), *Path.cwd().resolve().parents):
    if (utility_dir / "workshop_utils.py").is_file():
        if str(utility_dir) not in sys.path:
            sys.path.insert(0, str(utility_dir))
        break
else:
    raise FileNotFoundError("Start from the workshop root or a subdirectory.")

from workshop_utils import initialize_workshop

workshop_root, project_dir, data_dir, model_dir = initialize_workshop("control_zen_via_zenapi")

script_dir = Path(__file__).resolve().parent

PYRAMID_LEVELS = 3
SPATIAL_SHARD_SIZE_CHUNKS = 2


def main() -> None:
    """Run the configured example acquisition."""
    output = asyncio.run(
        stream_experiment(
            "ZEN_API_OMEZARR_Stream_Wellplate",
            zenapi_config=script_dir / "my_config.ini",
            output_dir=workshop_root / "results" / "streaming",
            start_experiment=True,
            channel_index=None,
            spatial_shard_size_chunks=SPATIAL_SHARD_SIZE_CHUNKS,
            pyramid_levels=PYRAMID_LEVELS,
            validate_ome_zarr=True,
        )
    )
    print(output)


if __name__ == "__main__":
    main()
