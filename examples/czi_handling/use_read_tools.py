import os
import sys
from pathlib import Path

# Direct interpreter launches do not apply Pixi's native-library PATH activation.
native_dll_dir = Path(sys.prefix) / "Library" / "bin"
if os.name == "nt" and native_dll_dir.is_dir():
    os.environ["PATH"] = str(native_dll_dir) + os.pathsep + os.environ.get("PATH", "")
import xarray as xr
from czitools.read_tools import read_tools
from czitools.utils.napari_tools import display_xarray_in_napari
from magicgui import magicgui
from magicgui.types import FileDialogMode

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


show_napari = True

# option to toggle using a file open dialog or a hardcoded filename
use_dialog = True


# open simple dialog to select a CZI file
@magicgui(
    filepath={
        "label": "Choose CZI files:",
        "mode": FileDialogMode.EXISTING_FILE,
        "filter": "*.czi",
        "value": data_dir,
    },
    call_button="Open CZI File",
)
def filespicker(filepath: Path) -> Path:
    """Take a filename and do something with it."""
    # Close the dialog after the file is selected and the button was pressed
    # This will also return the filepath to the caller
    filespicker.close()

    return filepath


if use_dialog:
    filespicker.filepath.changed.connect(print)
    filespicker.show(run=True)

    filepath = str(filespicker.filepath.value)
    print(f"Selected file: {filepath}")

elif not use_dialog:
    filepath = str(data_dir / "CellDivision_T10_Z15_CH2_DCV_small.czi")

# return a xarray with dimension order STCZYX(A)
# when no planes are specified the complete dataset
# when planes are specified the metadata will be adapted accordingly for SizeS, SizeT, SizeC and SizeZ
array6d, mdata = read_tools.read_6darray(
    filepath,
    zoom=1.0,
    planes={"S": (0, 0), "T": (0, 2), "C": (0, 0), "Z": (0, 4)},
    adapt_metadata=True,
    use_dask=False,
    use_xarray=True,
)

if array6d is None:
    raise RuntimeError("read_6darray returned no data.")
if not isinstance(array6d, xr.DataArray):
    raise TypeError(f"Expected an xarray DataArray, got {type(array6d).__name__}.")

# get the planes
subset_planes = array6d.attrs["subset_planes"]

# print the shape of the xarray etc.
print(f"Shape: {array6d.shape}")
print(f"Dimensions: {array6d.dims}")
print(f"Subset Planes: {subset_planes}")

for k, v in array6d.attrs.items():
    print(f"{k} :  {v}")

if show_napari:
    # Delegate Napari display to the utility function
    display_xarray_in_napari(array6d, mdata, subset_planes)
