"""Read CZI attachment images and display the slide preview.

Run directly in VS Code, or from the workshop repository root:
    pixi run --no-install python examples\\czi_handling\\read_attachment_images.py
"""

import os
import sys
from pathlib import Path

# Direct interpreter launches do not activate the Pixi environment's DLL paths.
if os.name == "nt":
    library_bin = Path(sys.prefix) / "Library" / "bin"
    if library_bin.is_dir():
        os.environ["PATH"] = str(library_bin) + os.pathsep + os.environ.get("PATH", "")

import matplotlib.pyplot as plt
from czitools.metadata_tools.attachment import CziAttachments
from czitools.metadata_tools.czi_metadata import CziMetadata
from czitools.metadata_tools.helper import AttachmentType
from czitools.read_tools import read_tools

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

# define the file location
filepath = data_dir / "w96_A1+A2.czi"
# filepath = data_dir / "Tumor_HE_Orig_small.czi"
# filepath = data_dir / "CellDivision_T=10_Z=15_CH=2_DCV_small.czi"

# read all metadata_tools and check for the attachment images
md = CziMetadata(filepath)

if md.attachments is None:
    raise RuntimeError(f"Attachment metadata is unavailable for {filepath}")

print(f"CZI Image has Label {md.attachments.has_label}")
print(f"CZI Image has SlidePreview {md.attachments.has_preview}")
print(f"CZI Image has Prescan {md.attachments.has_prescan}")

# get info about attachments only
attachments = CziAttachments(filepath)

for k, v in attachments.__dict__.items():
    print(k, v)

# read individual images as array and optionally copy the image files as CZIs
attachment_types = [AttachmentType.SlidePreview, AttachmentType.Label, AttachmentType.Prescan]

for at in attachment_types:
    if at == AttachmentType.SlidePreview and attachments.has_preview:
        # Read the slide preview attachment as an array and optionally copy it as a CZI file
        data, loc = read_tools.read_attachments(filepath, attachment_type=at, copy=True)

        if data is None:
            raise RuntimeError(f"Could not read the {at} attachment from {filepath}")
        print(f"Shape of {at} image: {data.shape}")
        print(f"Location of {at}: {loc}")

        preview = data[..., 0] if data.ndim == 3 and data.shape[-1] == 1 else data

        # Convert BGR to RGB if necessary
        if preview.ndim == 3 and preview.shape[-1] == 3:
            preview = preview[..., ::-1]  # Convert CZI BGR pixels to RGB.

        # show the slide preview image
        plt.figure()
        plt.imshow(preview, cmap="gray")
        plt.title(f"Slide preview: {Path(filepath).name}")
        plt.axis("off")
        plt.show(block=True)

    if at == AttachmentType.Label and attachments.has_label:
        data, loc = read_tools.read_attachments(filepath, attachment_type=at, copy=True)

        if data is None:
            raise RuntimeError(f"Could not read the {at} attachment from {filepath}")

        print(f"Shape of {at} image: {data.shape}")
        print(f"Location of {at}: {loc}")

    if at == AttachmentType.Prescan and attachments.has_prescan:
        data, loc = read_tools.read_attachments(filepath, attachment_type=at, copy=True)

        if data is None:
            raise RuntimeError(f"Could not read the {at} attachment from {filepath}")

        print(f"Shape of {at} image: {data.shape}")
        print(f"Location of {at}: {loc}")
