"""Demo: using read_stacks() from czitools.read_tools.

This script demonstrates the read_stacks() function which reads all 2D planes
from a CZI file, grouped per stack. It supports:
  - Lazy loading via dask arrays
  - xarray DataArrays with labeled dimensions
  - Optional stacking of scenes with matching shapes

Dimension order is always: [V, R, I, H, M] + T + C + Z + Y + X [+ A]
"""

import os
import sys
from pathlib import Path

# Direct interpreter launches do not apply Pixi's native-library PATH activation.
native_dll_dir = Path(sys.prefix) / "Library" / "bin"
if os.name == "nt" and native_dll_dir.is_dir():
    os.environ["PATH"] = str(native_dll_dir) + os.pathsep + os.environ.get("PATH", "")

import xarray as xr
from czitools.metadata_tools.czi_metadata import CziMetadata
from czitools.read_tools import read_tools
from czitools.utils.napari_tools import display_xarray_in_napari, display_xarray_list_in_napari

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

# Test files
filepath = data_dir / "WP96_4Pos_B4-10_DAPI.czi"


# show resulting stack inside napari
show_napari = True
# If result is a list of stacks, choose display mode:
# - True: show all stacks in one viewer
# - False: show only one stack selected by ``list_stack_index``
show_all_list_stacks = True
# Stack index used when ``result`` is a list and ``show_all_list_stacks`` is False.
# Ignored when result is not a list.
list_stack_index = 0

if __name__ == "__main__":
    # Read scenes using the new function from czitools.read_tools
    # Options:
    #   use_dask=True  -> lazy loading (data read only when accessed)
    #   use_xarray=True -> returns xr.DataArray with labeled dimensions
    #   stack_scenes=True -> combine scenes if they have the same shape

    mdata = CziMetadata(filepath)

    result, dims, num_stacks, mdata = read_tools.read_stacks(
        filepath,
        use_dask=True,
        use_xarray=True,
        stack_scenes=True,
    )

    print("\n=== Results ===")
    print(f"Number of stacks: {num_stacks}")
    print(f"Dimension order: {dims}")

    if isinstance(result, list):
        # List of per-scene arrays
        for idx, arr in enumerate(result):
            if isinstance(arr, xr.DataArray):
                print(f"Stack {idx}: dims={arr.dims}, shape={arr.shape}, dtype={arr.dtype}")
            else:
                print(f"Stack {idx}: shape={arr.shape}, dims={dims}, dtype={arr.dtype}")
    else:
        # Single stacked array
        if isinstance(result, xr.DataArray):
            print(f"Stacked: dims={result.dims}, shape={result.shape}, dtype={result.dtype}")
        else:
            print(f"Stacked: shape={result.shape}, dims={dims}, dtype={result.dtype}")

        # With use_dask=True, result is backed by dask - no data loaded yet
        print(f"\nArray shape (no data loaded): {result.shape}")

    if show_napari:
        if isinstance(result, list):
            if len(result) == 0:
                raise RuntimeError("No stack data available for Napari display.")

            if show_all_list_stacks:
                display_xarray_list_in_napari(result, mdata)
            else:
                selected_index = max(0, min(list_stack_index, len(result) - 1))
                stack = result[selected_index]
                subset_planes = stack.attrs.get("subset_planes", {}) if isinstance(stack, xr.DataArray) else {}
                print(f"Showing stack index: {selected_index}")
                display_xarray_in_napari(stack, mdata, subset_planes)
        else:
            subset_planes = result.attrs.get("subset_planes", {}) if isinstance(result, xr.DataArray) else {}
            display_xarray_in_napari(result, mdata, subset_planes)
