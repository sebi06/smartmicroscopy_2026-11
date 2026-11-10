"""CZI and OME-Zarr plate metadata and per-field reader preparation."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from czitools.metadata_tools import CziMetadata
from czitools.read_tools import read_field, read_stacks

ReaderBackend = Literal["read_stacks", "read_field"]
InputFormat = Literal["auto", "czi", "omezarr"]


def _open_omezarr_store(path: Path) -> Any:
    """Open an NGFF directory or ZIP archive without modifying it."""
    import zarr

    if path.is_dir():
        return zarr.storage.LocalStore(str(path), read_only=True)
    return zarr.storage.ZipStore(str(path), mode="r")


@dataclass
class OmeZarrWell:
    """NGFF well identity used by the shared well summarizer."""

    canonical_name: str
    canonical_path: str


@dataclass
class OmeZarrHcs:
    """Wells declared by an NGFF plate."""

    wells: list[OmeZarrWell]


@dataclass
class OmeZarrChannels:
    """Stored channel labels and RGB display colors."""

    names: list[str]
    colors: list[str]


@dataclass
class OmeZarrPlate:
    """Read-only NGFF plate adapter for the existing assay pipeline.

    Field indices follow plate-well and well-image metadata order. They are
    not original CZI scene indices. Only metadata are read during setup;
    read_field loads one full-resolution field and closes its store.
    """

    path: Path
    hcs: OmeZarrHcs
    channelinfo: OmeZarrChannels
    pixel_spacing_um: tuple[float, float]
    scene_wells: dict[int, str]
    field_paths: dict[int, str]
    field_specs: dict[int, tuple[str, tuple[str, ...]]]

    def read_field(self, scene_index: int) -> Any:
        """Load one field as an uppercase-axis xarray DataArray."""
        import numpy as np
        import xarray as xr
        import zarr

        array_path, axes = self.field_specs[scene_index]
        with _open_omezarr_store(self.path) as store:
            root = zarr.open_group(store=store, mode="r", use_consolidated=False)
            pixels = np.asarray(root[array_path][:])
        return xr.DataArray(
            pixels,
            dims=axes,
            coords={"C": self.channelinfo.names},
            attrs={"ngff_path": self.field_paths[scene_index]},
        )


def prepare_omezarr_plate(path: Path) -> OmeZarrPlate:
    """Inspect an NGFF directory or OZX without loading image pixels.

    Supports NGFF axes/scale metadata and NGFF 0.6 intrinsic coordinate
    systems with scale/translation sequences. Requires consistent channels
    and physical XY spacing across fields, with singleton time/Z axes.
    Missing metadata are errors; channel identities and spacing are not guessed.
    """
    import numpy as np
    import zarr

    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Input OME-Zarr plate not found: {path}")
    wells: list[OmeZarrWell] = []
    scene_wells: dict[int, str] = {}
    field_paths: dict[int, str] = {}
    field_specs: dict[int, tuple[str, tuple[str, ...]]] = {}
    channelinfo = None
    spacing = None
    unit_to_um = {"micrometer": 1.0, "nanometer": 0.001, "millimeter": 1000.0, "meter": 1e6}

    def ome_attributes(group: Any) -> dict[str, Any]:
        """Unwrap the NGFF 0.5/0.6 namespace or legacy attributes."""
        attributes = dict(group.attrs)
        return attributes.get("ome", attributes)

    with _open_omezarr_store(path) as store:
        root = zarr.open_group(store=store, mode="r", use_consolidated=False)
        plate = ome_attributes(root).get("plate")
        if not plate or not plate.get("wells"):
            raise ValueError("The OME-Zarr input must contain an NGFF HCS plate with wells.")
        for well in plate["wells"]:
            well_path = well["path"]
            row, column = well_path.split("/")
            name = f"{row.upper()}{int(column)}"
            if name in {item.canonical_name for item in wells}:
                raise ValueError(f"Duplicate NGFF well: {name}")
            wells.append(OmeZarrWell(name, well_path))
            well_metadata = ome_attributes(root[well_path]).get("well", {})
            for image in well_metadata.get("images", []):
                field_path = f"{well_path}/{image['path']}"
                if field_path in field_paths.values():
                    raise ValueError(f"Duplicate NGFF field path: {field_path}")
                attributes = ome_attributes(root[field_path])
                multiscales = attributes.get("multiscales", [])
                if len(multiscales) != 1:
                    raise ValueError(f"Expected one multiscale image at {field_path}.")
                multiscale = multiscales[0]
                dataset = multiscale["datasets"][0]
                axes = multiscale.get("axes")
                if axes is None:
                    systems = multiscale.get("coordinateSystems", [])
                    axes = next((system["axes"] for system in systems if system["name"] == "intrinsic"), None)
                if not axes:
                    raise ValueError(f"Missing NGFF axes at {field_path}.")
                dimensions = tuple(axis["name"].upper() for axis in axes)
                array_path = f"{field_path}/{dataset['path']}"
                array = root[array_path]
                sizes = dict(zip(dimensions, array.shape, strict=True))
                if len(sizes) != len(dimensions) or not {"C", "Y", "X"}.issubset(sizes):
                    raise ValueError(f"Expected unique C/Y/X axes at {field_path}: {dimensions}")
                if any(size != 1 for axis, size in sizes.items() if axis not in ("C", "Y", "X")):
                    raise ValueError(f"The assay requires 2D channel planes at {field_path}: {sizes}")

                scale = np.ones(len(axes), dtype=float)
                has_scale = False
                transformations = list(dataset.get("coordinateTransformations", []))
                while transformations:
                    transform = transformations.pop(0)
                    kind = transform["type"]
                    if kind == "sequence":
                        transformations[0:0] = transform["transformations"]
                    elif kind == "scale":
                        scale *= np.asarray(transform["scale"], dtype=float)
                        has_scale = True
                    elif kind not in ("translation", "identity"):
                        raise ValueError(f"Unsupported NGFF transform {kind!r} at {field_path}.")
                if not has_scale:
                    raise ValueError(f"Missing NGFF physical scale at {field_path}.")
                field_spacing = []
                for axis_name in ("Y", "X"):
                    axis_index = dimensions.index(axis_name)
                    unit = axes[axis_index].get("unit")
                    if unit not in unit_to_um:
                        raise ValueError(f"Unsupported spatial unit {unit!r} at {field_path}.")
                    field_spacing.append(float(scale[axis_index]) * unit_to_um[unit])
                if not all(np.isfinite(value) and value > 0 for value in field_spacing):
                    raise ValueError(f"Invalid XY pixel spacing at {field_path}: {field_spacing}")
                channels = attributes.get("omero", {}).get("channels", [])
                field_channels = OmeZarrChannels(
                    [channel["label"] for channel in channels],
                    [channel["color"] for channel in channels],
                )
                if len(channels) != sizes["C"] or not all(field_channels.names):
                    raise ValueError(f"Missing channel labels/colors at {field_path}.")
                if channelinfo is None:
                    channelinfo = field_channels
                    spacing = (field_spacing[0], field_spacing[1])
                elif channelinfo != field_channels or not np.allclose(spacing, field_spacing, rtol=1e-9, atol=0):
                    raise ValueError(f"Inconsistent channels or XY spacing at {field_path}.")
                scene_index = len(scene_wells)
                scene_wells[scene_index] = name
                field_paths[scene_index] = field_path
                field_specs[scene_index] = (array_path, dimensions)
    if channelinfo is None or spacing is None:
        raise ValueError("No NGFF fields are available for analysis.")
    return OmeZarrPlate(path, OmeZarrHcs(wells), channelinfo, spacing, scene_wells, field_paths, field_specs)


def resolve_input_format(path: Path, input_format: InputFormat = "auto") -> Literal["czi", "omezarr"]:
    """Detect supported local input containers and reject format mismatches."""
    path = Path(path)
    if input_format not in ("auto", "czi", "omezarr"):
        raise ValueError(f"Unsupported input format: {input_format}")
    if not path.exists():
        raise FileNotFoundError(f"Assay input not found: {path}")
    detected: Literal["czi", "omezarr"]
    if path.is_file() and path.suffix.lower() == ".czi":
        detected = "czi"
    elif path.is_file() and path.suffix.lower() in (".ozx", ".zip"):
        detected = "omezarr"
    elif path.is_dir() and any((path / name).is_file() for name in ("zarr.json", ".zgroup")):
        detected = "omezarr"
    else:
        raise ValueError("Choose a CZI file, an OME-Zarr directory, or an OZX archive.")
    if input_format != "auto" and input_format != detected:
        raise ValueError(f"Requested {input_format} input but {path.name} is {detected}.")
    return detected


@dataclass
class AssayInput:
    """Normalized input metadata and readers for the format-neutral notebook."""

    path: Path
    input_format: Literal["czi", "omezarr"]
    metadata: CziMetadata | OmeZarrPlate
    scene_wells: dict[int, str]
    pixel_spacing_um: tuple[float, float]
    field_paths: dict[int, str]
    field_index_meaning: str
    reader_backend: str
    preview_reader: Callable[[int], Any]

    def prepare_scene_inputs(self) -> tuple[list[Any] | None, Any, int, Callable[[int], Any] | None]:
        """Defer analysis-reader preparation until after preview/layout checks."""
        if isinstance(self.metadata, OmeZarrPlate):
            return None, "NGFF C/Y/X planes with singleton outer axes", len(self.scene_wells), self.preview_reader
        if self.reader_backend not in ("read_stacks", "read_field"):
            raise ValueError(f"Unsupported CZI reader backend: {self.reader_backend}")
        return prepare_scene_inputs(self.path, self.metadata, self.reader_backend)


def load_assay_input(
    path: Path,
    input_format: InputFormat = "auto",
    czi_reader_backend: ReaderBackend = "read_stacks",
) -> AssayInput:
    """Normalize CZI, NGFF directory, or OZX metadata without plate-wide reads.

    CZI field identifiers retain stored scene indices. NGFF identifiers follow
    declared well/image order and retain exact image paths for provenance.
    The CZI integrity report is separate so notebook callers can display it.
    """
    import numpy as np

    path = Path(path).resolve()
    detected = resolve_input_format(path, input_format)
    if czi_reader_backend not in ("read_stacks", "read_field"):
        raise ValueError(f"Unsupported CZI reader backend: {czi_reader_backend}")
    if detected == "omezarr":
        plate = prepare_omezarr_plate(path)
        return AssayInput(
            path, detected, plate, plate.scene_wells, plate.pixel_spacing_um,
            plate.field_paths, "NGFF plate-well / well-image order; not original CZI scene IDs",
            "omezarr_zip_field" if path.is_file() else "omezarr_directory_field", plate.read_field,
        )
    metadata = CziMetadata(str(path))
    mapping = scene_to_well(metadata)
    scale = metadata.scale_required
    if scale.Y is None or scale.X is None:
        raise ValueError("CZI metadata do not contain XY pixel scaling.")
    spacing = (float(scale.Y), float(scale.X))
    if not all(np.isfinite(value) and value > 0 for value in spacing):
        raise ValueError(f"Invalid XY pixel spacing: {spacing}")
    _, _, _, preview_reader = prepare_scene_inputs(path, metadata, "read_field")
    assert preview_reader is not None
    assert metadata.hcs is not None
    field_paths = {
        field.scene_index: f"{well.canonical_path}/field/{field.field_index}"
        for well in metadata.hcs.wells
        for field in well.fields
    }
    return AssayInput(
        path, detected, metadata, mapping, spacing, field_paths,
        "Original zero-based stored CZI scene index", czi_reader_backend, preview_reader,
    )


def run_hcs_check(czi_path: Path) -> None:
    """Forward the HCS integrity report to console or notebook output."""
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    report = subprocess.run(
        [sys.executable, "-m", "czitools.hcs_check", str(czi_path)],
        check=False,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    print(report.stdout, end="")
    report.check_returncode()


def scene_to_well(metadata: CziMetadata) -> dict[int, str]:
    """Map stored scene indices to normalized HCS well names."""
    if metadata.hcs is None:
        reason = metadata.hcs_status.reason if metadata.hcs_status else "not detected"
        raise ValueError(f"No usable HCS plate metadata: {reason}")

    mapping: dict[int, str] = {}
    for well in metadata.hcs.wells:
        for field in well.fields:
            if field.scene_index in mapping:
                raise ValueError(f"Scene {field.scene_index} maps to more than one well.")
            mapping[field.scene_index] = well.canonical_name
    return mapping


def prepare_scene_inputs(
    czi_path: Path,
    metadata: CziMetadata,
    reader_backend: ReaderBackend = "read_stacks",
) -> tuple[list[Any] | None, Any, int, Callable[[int], Any] | None]:
    """Prepare lazy scene arrays or a deferred well/field reader.

    Returns:
        Scene arrays (or None), dimension description, field count, and a
        field-loading callback (or None). Exactly one input source is active.
    """
    if reader_backend not in ("read_stacks", "read_field"):
        raise ValueError(f"Unsupported reader backend: {reader_backend}")
    scene_wells = scene_to_well(metadata)
    if not scene_wells:
        raise ValueError("No mapped HCS fields are available for analysis.")

    if reader_backend == "read_field":
        assert metadata.hcs is not None
        # HCS field indices are well-local; stored scene indices remain the
        # identifiers used for measurements, progress, and preview selection.
        field_selectors = {
            field.scene_index: (well.canonical_name, field.field_index)
            for well in metadata.hcs.wells
            for field in well.fields
        }

        def load_field(scene_index: int) -> Any:
            well_name, field_index = field_selectors[scene_index]
            reader_logger = logging.getLogger("czitools")
            previous_level = reader_logger.level
            reader_logger.setLevel(logging.WARNING)
            try:
                # read_field uses eager read_6darray internally. Read only the
                # requested field here, never collect a whole well or plate.
                # use_dask=True would merely wrap already-loaded pixels.
                array, _ = read_field(
                    czi_path,
                    well_name,
                    field_index,
                    use_dask=False,
                    use_xarray=True,
                )
            finally:
                reader_logger.setLevel(previous_level)
            if array is None:
                raise ValueError(f"Could not read well {well_name}, field {field_index} " f"(scene {scene_index}).")
            return array

        # Constructing the callback does not read pixels. The shared analysis
        # loop invokes it immediately before processing each mapped scene.
        return None, "STCZYX(A)", len(field_selectors), load_field

    # Preserve the original genuinely lazy path as the default. Reader setup
    # may read representative pixels, but field computation happens later.
    reader_logger = logging.getLogger("czitools")
    previous_level = reader_logger.level
    reader_logger.setLevel(logging.WARNING)
    try:
        scene_arrays, dimensions, scene_count, _ = read_stacks(
            str(czi_path),
            use_dask=True,
            use_xarray=True,
            metadata=metadata,
        )
    finally:
        reader_logger.setLevel(previous_level)
    if not isinstance(scene_arrays, list):
        scene_arrays = [scene_arrays]
    if scene_count != len(scene_arrays):
        raise ValueError(f"czitools reported {scene_count} scenes but returned " f"{len(scene_arrays)} image arrays.")
    missing_scenes = set(scene_wells) - set(range(len(scene_arrays)))
    if missing_scenes:
        raise ValueError(f"HCS scene indices were not read: {sorted(missing_scenes)}")
    if not scene_arrays:
        raise ValueError("No CZI scenes were returned by czitools.read_stacks.")
    return scene_arrays, dimensions, scene_count, None
