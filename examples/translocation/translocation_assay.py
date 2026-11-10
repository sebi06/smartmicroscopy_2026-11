"""Run a CZI or OME-Zarr nuclear-to-cytoplasmic translocation assay.

The workflow validates plate metadata, reads each field, segments
DAPI-positive nuclei, measures EGFP in nuclei and surrounding rings, and
writes per-cell/per-well tables with dose-response plots. Inputs can be
CZI files, OME-Zarr HCS plate directories, or OZX archives.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from translocation_assay_io import (
    InputFormat,
    ReaderBackend,
    load_assay_input,
    resolve_input_format,
)
from translocation_assay_io import (
    run_hcs_check as _run_hcs_check,
)
from translocation_assay_utils import (
    THRESHOLD_METHODS,
    PlotBackend,
    ThresholdMethod,
    analyze_scenes,
    write_analysis_outputs,
)
from translocation_plate_layout import build_plate_layout as _plate_layout
from translocation_plate_layout import load_plate_layout

LOGGER = logging.getLogger("translocation_assay")

CHANNELINDEX_PRIMARY_OBJECT = 0
CHANNELINDEX_SECONDARY_OBJECT = 1
SEGMENTATION_SCENE = None


def _default_czi_path() -> Path:
    """Return the assay input from the workshop's shared data directory."""
    return Path(__file__).resolve().parents[2] / "data" / "translocation" / "transloc_gfp_dapi_0_2micron.czi"


def run_analysis(
    czi_path: Path,
    output_dir: Path,
    ring_width_um: float | None,
    min_nucleus_area_px: int,
    min_nucleus_distance_px: int,
    ratio_threshold: float,
    ring_width_px: float | None = None,
    plot_backend: PlotBackend = "seaborn",
    segmentation_scene: int | None = SEGMENTATION_SCENE,
    reader_backend: ReaderBackend = "read_stacks",
    plate_layout_path: Path | None = None,
    threshold_method: ThresholdMethod = "otsu",
    input_format: InputFormat = "auto",
) -> None:
    """Run metadata validation, field processing, aggregation, and plotting.

    czi_path retains its historical name for Python-call compatibility, but
    accepts a CZI, an OME-Zarr plate directory, or an OZX archive. input_format
    detects the container by default; explicit czi/omezarr must match it.

    The ring-width parameters are alternative units for one width, not two
    independent settings. Set exactly one to a finite positive value and the
    other to None: ring_width_um=2.0, ring_width_px=None uses micrometers;
    ring_width_um=None, ring_width_px=10.0 uses pixels. Micrometer mode uses
    input pixel scaling; 2.0 micrometers equals 10 pixels only at 0.2 um/pixel.
    Supplying both widths or neither width is invalid for this Python API.

    For CZI, reader_backend selects lazy read_stacks (default) or eager
    read_field calls performed one field at a time. NGFF sources always use
    read-only, full-resolution field reads without extracting OZX archives.
    All readers share the analysis pipeline. field_mapping.csv preserves
    source paths; NGFF field IDs are not original CZI scene indices.
    plate_layout_path optionally selects a validated Excel Wells sheet instead
    of the built-in assignments. Workbook annotations are saved with results.
    When plate_layout_path is None (the default), build_plate_layout() supplies
    the built-in layout; plate_layout_example.xlsx is not loaded automatically.
    To use that workbook from the CLI, pass
    --plate-layout data/translocation/plate_layout_example.xlsx from the workshop root.
    threshold_method selects global DAPI thresholding; the default is Otsu.
    """
    if (ring_width_um is None) == (ring_width_px is None):
        raise ValueError("Specify exactly one ring width in microns or pixels.")
    requested_ring_width = ring_width_um if ring_width_um is not None else ring_width_px
    if requested_ring_width is None or not np.isfinite(requested_ring_width) or requested_ring_width <= 0:
        raise ValueError("Ring width must be a finite value greater than zero.")
    if min_nucleus_area_px < 1 or min_nucleus_distance_px < 1:
        raise ValueError("Nucleus area and peak distance must be positive integers.")
    if ratio_threshold <= 0:
        raise ValueError("Translocation ratio threshold must be greater than zero.")
    if plot_backend not in ("plotly", "seaborn"):
        raise ValueError(f"Unsupported plot backend: {plot_backend}")
    if reader_backend not in ("read_stacks", "read_field"):
        raise ValueError(f"Unsupported reader backend: {reader_backend}")
    if threshold_method not in THRESHOLD_METHODS:
        raise ValueError(f"Unsupported threshold method: {threshold_method}")

    input_path = Path(czi_path)
    detected_format = resolve_input_format(input_path, input_format)
    plate_layout = load_plate_layout(plate_layout_path) if plate_layout_path is not None else _plate_layout()
    if detected_format == "czi":
        LOGGER.info("Running czitools HCS_check on %s", input_path)
        _run_hcs_check(input_path)
    assay_input = load_assay_input(input_path, input_format, reader_backend)
    metadata = assay_input.metadata
    scene_wells = assay_input.scene_wells
    if plate_layout_path is not None and (missing_wells := set(scene_wells.values()) - set(plate_layout)):
        raise ValueError(f"Acquired wells are missing from the layout: {sorted(missing_wells)}")
    if metadata.hcs is None:
        raise ValueError("No HCS plate is available for analysis.")
    pixel_spacing_um = assay_input.pixel_spacing_um
    LOGGER.info("Input format: %s; reader: %s", assay_input.input_format, assay_input.reader_backend)
    output_dir.mkdir(parents=True, exist_ok=True)

    if ring_width_um is not None:
        ring_width_equivalent_um_yx = (ring_width_um, ring_width_um)
        ring_width_equivalent_px_yx = (
            ring_width_um / pixel_spacing_um[0],
            ring_width_um / pixel_spacing_um[1],
        )
        ring_width_label = (
            f"{ring_width_um:g} um "
            f"({ring_width_equivalent_px_yx[0]:g} px Y, "
            f"{ring_width_equivalent_px_yx[1]:g} px X)"
        )
    else:
        assert ring_width_px is not None
        ring_width_equivalent_px_yx = (ring_width_px, ring_width_px)
        ring_width_equivalent_um_yx = (
            ring_width_px * pixel_spacing_um[0],
            ring_width_px * pixel_spacing_um[1],
        )
        ring_width_label = (
            f"{ring_width_px:g} px "
            f"({ring_width_equivalent_um_yx[0]:g} um Y, "
            f"{ring_width_equivalent_um_yx[1]:g} um X)"
        )
    if metadata.channelinfo is None:
        raise ValueError("Channel metadata are unavailable.")
    channel_names = list(metadata.channelinfo.names)
    channel_indices = {
        "EGFP": CHANNELINDEX_PRIMARY_OBJECT,
        "DAPI": CHANNELINDEX_SECONDARY_OBJECT,
    }
    for channel, index in channel_indices.items():
        if index >= len(channel_names):
            raise ValueError(
                f"Channel index {index} for {channel} is unavailable; " f"stored channels are {channel_names}."
            )
        if channel_names[index].strip().casefold() != channel.casefold():
            raise ValueError(f"Expected {channel} at channel index {index}; " f"stored channels are {channel_names}.")
    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    ) as progress:
        preparation_label = (
            "Prepare lazy scenes" if assay_input.reader_backend == "read_stacks" else "Prepare field reader"
        )
        preparation_task = progress.add_task(preparation_label, total=None)
        scene_arrays, dimensions, scene_count, field_reader = assay_input.prepare_scene_inputs()
        progress.update(preparation_task, total=scene_count, completed=scene_count)
        processing_task = progress.add_task("Process fields", total=scene_count)

        results = analyze_scenes(
            metadata=metadata,
            scene_arrays=scene_arrays,
            scene_wells=scene_wells,
            channel_indices=channel_indices,
            pixel_spacing_um=pixel_spacing_um,
            dimensions=dimensions,
            min_nucleus_area_px=min_nucleus_area_px,
            min_nucleus_distance_px=min_nucleus_distance_px,
            threshold_method=threshold_method,
            ratio_threshold=ratio_threshold,
            ring_width_um=ring_width_um,
            ring_width_px=ring_width_px,
            plate_layout=plate_layout,
            segmentation_scene=segmentation_scene,
            field_reader=field_reader,
            progress_callback=lambda completed, total: progress.update(
                processing_task,
                completed=completed,
                total=total,
            ),
        )
    parameters = {
        "InputPath": str(assay_input.path),
        "InputFormat": assay_input.input_format,
        "InputFormatRequested": input_format,
        "CziReaderBackendRequested": reader_backend,
        "NgffResolutionLevel": 0 if assay_input.input_format == "omezarr" else None,
        "FieldIndexMeaning": assay_input.field_index_meaning,
        "FieldMappingFile": "field_mapping.csv",
        "Channels": {
            "EGFP": channel_names[channel_indices["EGFP"]],
            "DAPI": channel_names[channel_indices["DAPI"]],
        },
        "ChannelIndices": channel_indices,
        "PixelSpacingUmYX": list(pixel_spacing_um),
        "RingWidthUm": ring_width_um,
        "RingWidthPx": ring_width_px,
        "RingWidthEquivalentUmYX": list(ring_width_equivalent_um_yx),
        "RingWidthEquivalentPxYX": list(ring_width_equivalent_px_yx),
        "RingWidthLabel": ring_width_label,
        "MinNucleusAreaPx": min_nucleus_area_px,
        "MinNucleusDistancePx": min_nucleus_distance_px,
        "DapiThresholdMethod": threshold_method,
        "TranslocationRatioThreshold": ratio_threshold,
        "PlotBackend": plot_backend,
        "ReaderBackend": assay_input.reader_backend,
        "SegmentationSceneRequested": segmentation_scene,
        "SegmentationSceneShown": (
            results.segmentation_example[4] if results.segmentation_example is not None else None
        ),
        "FieldsProcessed": results.fields_processed,
        "ObjectsDetected": len(results.cell_table),
    }
    if assay_input.input_format == "czi":
        parameters["InputCzi"] = str(czi_path)
    else:
        parameters["InputOmeZarr"] = str(assay_input.path)
    pd.DataFrame(
        [
            {"SceneIndex": index, "Well": well, "FieldPath": assay_input.field_paths[index]}
            for index, well in sorted(scene_wells.items())
        ]
    ).to_csv(output_dir / "field_mapping.csv", index=False)
    if plate_layout_path is not None:
        parameters["PlateLayoutFile"] = str(plate_layout_path.resolve())
        parameters["PlateLayoutSnapshot"] = "plate_layout_used.csv"
        pd.DataFrame([{"Well": well, **assignment} for well, assignment in plate_layout.items()]).to_csv(
            output_dir / "plate_layout_used.csv",
            index=False,
        )
    write_analysis_outputs(results, output_dir, parameters, plot_backend)


def main(argv: list[str] | None = None) -> int:
    """Parse command-line options and run the assay workflow."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        "--czi",
        dest="input_path",
        type=Path,
        default=_default_czi_path(),
        help=(
            "Input CZI, OME-Zarr HCS directory, or OZX archive (--czi is a legacy alias). "
            "Default: workshop data/translocation/transloc_gfp_dapi_0_2micron.czi."
        ),
    )
    parser.add_argument(
        "--input-format",
        choices=("auto", "czi", "omezarr"),
        default="auto",
        help="Detect input format (default) or require czi/omezarr; mismatches are rejected.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "results" / "translocation",
        help="Output folder (default: workshop results/translocation).",
    )
    parser.add_argument(
        "--plate-layout",
        type=Path,
        help=(
            "Excel workbook with a Wells sheet (default: built-in layout, not an Excel file). "
            "To use the example workbook, pass --plate-layout data/translocation/plate_layout_example.xlsx; "
            "relative paths are resolved from the working directory."
        ),
    )
    # Alternative units for one width; the CLI defaults to 2.0 um if omitted.
    ring_width_group = parser.add_mutually_exclusive_group()
    ring_width_group.add_argument(
        "--ring-width-um",
        type=float,
        help=(
            "Ring width in micrometers using input pixel scaling; alternative to "
            "--ring-width-px (default: 2.0 if neither option is given)."
        ),
    )
    ring_width_group.add_argument(
        "--ring-width-px",
        type=float,
        help=(
            "Ring width directly in pixels; alternative to --ring-width-um. " "Do not supply both ring-width options."
        ),
    )
    parser.add_argument("--min-nucleus-area-px", type=int, default=40)
    parser.add_argument("--min-nucleus-distance-px", type=int, default=8)
    parser.add_argument(
        "--threshold-method",
        choices=tuple(THRESHOLD_METHODS),
        default="otsu",
        help="Global DAPI threshold for primary-object segmentation (default: otsu).",
    )
    parser.add_argument("--ratio-threshold", type=float, default=2.0)
    parser.add_argument(
        "--segmentation-scene",
        type=int,
        default=SEGMENTATION_SCENE,
        help=(
            "Stored CZI scene ID or NGFF field ID for the segmentation preview "
            "(default: first field with nuclei). See field_mapping.csv."
        ),
    )
    parser.add_argument(
        "--reader-backend",
        choices=("read_stacks", "read_field"),
        default="read_stacks",
        help=(
            "CZI only: lazy scene arrays (default) or eager reads by well/field. "
            "OME-Zarr/OZX always reads one full-resolution field at a time."
        ),
    )
    parser.add_argument(
        "--plot-backend",
        choices=("plotly", "seaborn"),
        default="plotly",
        help="Plotly writes interactive HTML; Seaborn writes static PNG files.",
    )
    args = parser.parse_args(argv)

    input_path = args.input_path
    try:
        resolve_input_format(input_path, args.input_format)
    except (FileNotFoundError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2

    output_dir = args.output_dir
    ring_width_um = args.ring_width_um
    if ring_width_um is None and args.ring_width_px is None:
        ring_width_um = 2.0
    try:
        run_analysis(
            czi_path=input_path,
            output_dir=output_dir,
            ring_width_um=ring_width_um,
            min_nucleus_area_px=args.min_nucleus_area_px,
            min_nucleus_distance_px=args.min_nucleus_distance_px,
            threshold_method=args.threshold_method,
            ratio_threshold=args.ratio_threshold,
            ring_width_px=args.ring_width_px,
            plot_backend=args.plot_backend,
            segmentation_scene=args.segmentation_scene,
            reader_backend=args.reader_backend,
            plate_layout_path=args.plate_layout,
            input_format=args.input_format,
        )
    except Exception:
        LOGGER.exception("Translocation assay failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
