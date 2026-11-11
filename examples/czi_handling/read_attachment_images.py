import os
from pathlib import Path

from czitools.metadata_tools.attachment import CziAttachments
from czitools.metadata_tools.czi_metadata import CziMetadata
from czitools.metadata_tools.helper import AttachmentType
from czitools.read_tools import read_tools

# adapt to your needs
defaultdir = Path(Path(__file__).resolve().parents[2]) / "data"
os.chdir(defaultdir)

# define the file location
filepath = r"w96_A1+A2.czi"
# filepath = r"Tumor_HE_Orig_small.czi"
# filepath = r"CellDivision_T=10_Z=15_CH=2_DCV_small.czi"

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
    if at == "SlidePreview" and attachments.has_preview:
        data, loc = read_tools.read_attachments(filepath, attachment_type=at, copy=True)
        if data is None:
            raise RuntimeError(f"Could not read the {at} attachment from {filepath}")
        print(f"Shape of {at} image: {data.shape}")
        print(f"Location of {at}: {loc}")

    if at == "Label" and attachments.has_label:
        data, loc = read_tools.read_attachments(filepath, attachment_type=at, copy=True)
        if data is None:
            raise RuntimeError(f"Could not read the {at} attachment from {filepath}")
        print(f"Shape of {at} image: {data.shape}")
        print(f"Location of {at}: {loc}")

    if at == "Prescan" and attachments.has_prescan:
        data, loc = read_tools.read_attachments(filepath, attachment_type=at, copy=True)
        if data is None:
            raise RuntimeError(f"Could not read the {at} attachment from {filepath}")
        print(f"Shape of {at} image: {data.shape}")
        print(f"Location of {at}: {loc}")
