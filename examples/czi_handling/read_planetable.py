import sys
from pathlib import Path

from czitools.metadata_tools.czi_metadata import CziMetadata
from czitools.metadata_tools.dimension import CziDimensions
from czitools.utils import logging_tools, planetable
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

logger = logging_tools.set_logging()


# open simple dialog to select a CZI file
@magicgui(
    filepath={
        "label": "Choose CZI files:",
        "mode": FileDialogMode.EXISTING_FILE,
        "filter": "*.czi",
        "value": data_dir,
    },
    call_button="Read Plantable from CZI File",
)
def filespicker(filepath: Path) -> Path:
    """Take a filename and do something with it."""
    # Close the dialog after the file is selected and the button was pressed
    # This will return the filepath to the caller
    filespicker.close()

    return filepath


filespicker.filepath.changed.connect(print)
filespicker.show(run=True)

# Get the filepath and convert to string
filepath = str(filespicker.filepath.value)
logger.info(f"Selected file: {filepath}")

# get the metadata_tools at once as one big class
mdata = CziMetadata(filepath)

# get only specific metadata_tools
czi_dimensions = CziDimensions(filepath)
print("SizeS: ", czi_dimensions.SizeS)
print("SizeT: ", czi_dimensions.SizeT)
print("SizeZ: ", czi_dimensions.SizeZ)
print("SizeC: ", czi_dimensions.SizeC)
print("SizeY: ", czi_dimensions.SizeY)
print("SizeX: ", czi_dimensions.SizeX)

# get the planetable for the CZI file with "normed" timestamps
pt1, _ = planetable.get_planetable(
    filepath,
    norm_time=True,
    save_table=True,
    planes={"time": 0, "channel": 0, "zplane": 0},
    include_pyramid=True,
)

print(pt1)
