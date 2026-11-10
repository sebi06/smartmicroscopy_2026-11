"""Processing, dose-response, and plotting helpers for the CZI assay."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast, get_type_hints

import numpy as np
import pandas as pd
from czitools.metadata_tools import CziMetadata
from numpy.typing import NDArray
from scipy import ndimage as ndi
from skimage.feature import peak_local_max
from skimage.filters import (
    threshold_isodata,
    threshold_li,
    threshold_mean,
    threshold_otsu,
    threshold_triangle,
    threshold_yen,
)
from skimage.morphology import remove_small_objects
from skimage.segmentation import relabel_sequential, watershed

from translocation_assay_io import OmeZarrPlate

LOGGER = logging.getLogger("translocation_assay")
PlotBackend = Literal["plotly", "seaborn"]
ThresholdMethod = Literal["otsu", "li", "yen", "triangle", "isodata", "mean"]
THRESHOLD_METHODS = {
    "otsu": threshold_otsu,
    "li": threshold_li,
    "yen": threshold_yen,
    "triangle": threshold_triangle,
    "isodata": threshold_isodata,
    "mean": threshold_mean,
}


@dataclass
class AssayResults:
    """Tables and plot inputs produced from the scanned CZI scenes."""

    cell_table: pd.DataFrame
    well_table: pd.DataFrame
    dose_table: pd.DataFrame
    fits: dict[str, tuple[dict[str, float] | None, str]]
    ec50_table: pd.DataFrame
    segmentation_example: tuple[np.ndarray, np.ndarray, np.ndarray, str, int, float, np.ndarray] | None
    fields_processed: int


def display_scrollable_table(
    table: pd.DataFrame,
    max_height_px: int = 320,
    *,
    max_rows: int | None = None,
    show_index: bool = False,
    show_row_count: bool = False,
) -> None:
    """Display a DataFrame with configurable preview and scrolling options.

    Args:
        table: DataFrame to display without modifying it.
        max_height_px: Positive maximum table height in pixels.
        max_rows: Positive preview row limit; None displays all rows.
        show_index: Include the DataFrame index.
        show_row_count: Report displayed and total row counts.
    """
    from IPython.display import HTML, display

    if isinstance(max_height_px, bool) or not isinstance(max_height_px, int) or max_height_px < 1:
        raise ValueError("max_height_px must be a positive integer.")
    if max_rows is not None and (isinstance(max_rows, bool) or not isinstance(max_rows, int) or max_rows < 1):
        raise ValueError("max_rows must be a positive integer or None.")

    preview_table = table if max_rows is None else table.head(max_rows)
    if show_row_count:
        if len(preview_table) == len(table):
            print(f"Showing all {len(table):,} rows.")
        else:
            print(f"Showing first {len(preview_table):,} of {len(table):,} rows.")
    display(
        HTML(
            f'<div style="max-height: {max_height_px}px; max-width: 100%; overflow: auto;">'
            + preview_table.to_html(index=show_index, max_rows=None, max_cols=None)
            + "</div>"
        )
    )


def make_channel_preview(egfp: np.ndarray, dapi: np.ndarray) -> Any:
    """Build a Stackview preview with a black image when both channels are off."""
    import stackview
    from ipywidgets import ToggleButton
    from matplotlib.colors import Normalize

    if egfp.ndim != 2 or dapi.shape != egfp.shape or not egfp.size:
        raise ValueError("The preview requires matching, nonempty 2D channels.")

    rgb_channels = [
        np.asarray(stackview.create_colormap(color)(Normalize()(image), bytes=True))[..., :3].astype(np.uint16)
        for image, color in ((egfp, "pure_green"), (dapi, "pure_blue"))
    ]

    def overlay(
        background: np.ndarray,
        is_egfp: bool = True,
        is_dapi: bool = True,
    ) -> np.ndarray:
        """Compose selected channels without modifying the input images."""
        composite = background.astype(np.uint16)
        if is_egfp:
            composite += rgb_channels[0]
        if is_dapi:
            composite += rgb_channels[1]
        return np.minimum(composite, 255).astype(np.uint8)

    return stackview.interact(
        overlay,
        np.zeros((*egfp.shape, 3), dtype=np.uint8),
        is_egfp=ToggleButton(value=True, description="EGFP"),
        is_dapi=ToggleButton(value=True, description="DAPI"),
    )


def make_field_tuner(
    initial_well: str,
    *,
    field_reader: Callable[[int], Any],
    scene_wells: dict[int, str],
    channel_indices: dict[str, int],
    pixel_spacing_um: tuple[float, float],
    min_nucleus_area_px: int = 40,
    min_nucleus_distance_px: int = 8,
    ring_width_um: float | None = 2.0,
    ring_width_px: float | None = None,
    ratio_threshold: float = 2.0,
    threshold_method: ThresholdMethod = "otsu",
) -> Any:
    """Build a Stackview field tuner without changing analysis settings.

    Args:
        initial_well: Acquired well to display initially.
        field_reader: Callback loading a stored scene as a channel-indexed
            xarray DataArray.
        scene_wells: Mapping from stored scene indices to well names.
        channel_indices: EGFP and DAPI channel positions in each field.
        pixel_spacing_um: Physical pixel sizes in (Y, X) order.
        min_nucleus_area_px: Initial minimum retained nucleus area in pixels.
        min_nucleus_distance_px: Initial watershed peak separation in pixels.
        ring_width_um: Initial physical ring width, or None for pixel mode.
        ring_width_px: Initial pixel ring width, or None for physical mode.
        ratio_threshold: Initial finite nucleus/ring response cutoff.
        threshold_method: Initial global DAPI threshold method.

    Returns:
        An ipywidgets VBox with well/field controls, overlays, and live counts.

    Raises:
        ValueError: If the initial well is absent or ring units are ambiguous.

    Notes:
        Widget dependencies are imported only when this function is called.
        Only the current field is cached. Slider changes do not modify input
        arrays, analysis settings, or exported results.
    """
    import ipywidgets as widgets
    import stackview
    from matplotlib.colors import Normalize
    from skimage.segmentation import find_boundaries

    scene_wells = dict(scene_wells)
    well_scenes = {
        well: sorted(scene for scene, name in scene_wells.items() if name == well)
        for well in sorted(set(scene_wells.values()))
    }
    if initial_well not in well_scenes:
        raise ValueError(f"No acquired fields for well {initial_well}.")
    if (ring_width_um is None) == (ring_width_px is None):
        raise ValueError("Specify exactly one ring width in micrometers or pixels.")
    if threshold_method not in THRESHOLD_METHODS:
        raise ValueError(f"Unsupported threshold method: {threshold_method}")
    channels = dict(channel_indices)
    spacing = pixel_spacing_um
    use_microns = ring_width_um is not None
    configured_width = ring_width_um if ring_width_um is not None else ring_width_px
    assert configured_width is not None

    well_control = widgets.Dropdown(
        options=list(well_scenes),
        value=initial_well,
        description="Well",
    )
    field_control = widgets.SelectionSlider(
        options=[
            (f"Field {number + 1} (scene {scene})", scene) for number, scene in enumerate(well_scenes[initial_well])
        ],
        description="Field",
        continuous_update=False,
        layout=widgets.Layout(width="500px", max_width="100%"),
    )
    status = widgets.HTML()

    @lru_cache(maxsize=1)
    def load_field(scene_index: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Keep only the current field in memory while parameters change."""
        field = field_reader(scene_index)
        egfp, dapi = (np.asarray(field.isel(C=channels[name]).squeeze(drop=True).values) for name in ("EGFP", "DAPI"))
        if egfp.ndim != 2 or dapi.shape != egfp.shape or not egfp.size:
            raise ValueError("The tuner requires matching, nonempty 2D channels.")
        composite = np.stack(
            (np.zeros(egfp.shape), Normalize()(egfp), Normalize()(dapi)),
            axis=-1,
        ).astype(np.float32)
        return egfp, dapi, composite

    def render_field(
        background: np.ndarray,
        scene_index: int = 0,
        min_area_px: int = 40,
        min_distance_px: int = 8,
        ring_width: float = 2.0,
        ratio_cutoff: float = 2.0,
        threshold_method: str = "otsu",
        show_nuclei: bool = True,
        show_rings: bool = True,
        show_responders: bool = True,
    ) -> np.ndarray:
        """Overlay nuclei, rings, and above-threshold nuclei on EGFP/DAPI."""
        egfp, dapi, composite = load_field(scene_index)
        nuclei, threshold = segment_nuclei(
            dapi,
            min_area_px=min_area_px,
            min_distance_px=min_distance_px,
            threshold_method=cast(ThresholdMethod, threshold_method),
        )
        rings = make_ring_labels(
            nuclei,
            ring_width_um=ring_width if use_microns else None,
            pixel_spacing_um=spacing,
            ring_width_px=None if use_microns else ring_width,
        )
        measurements = measure_scene_objects(
            egfp,
            nuclei,
            rings,
            spacing,
            scene_wells[scene_index],
            scene_index,
            threshold,
        )
        ratios = np.array([record["TranslocationRatio"] for record in measurements])
        valid = np.isfinite(ratios)
        responding = valid & (ratios >= ratio_cutoff)
        fraction = f"{responding.sum() / valid.sum():.1%}" if valid.any() else "n/a"
        status.value = (
            f"<b>Well {scene_wells[scene_index]}, scene {scene_index}</b>: "
            f"{len(measurements)} nuclei; {valid.sum()} valid ratios; "
            f"{fraction} at or above {ratio_cutoff:g}; "
            f"DAPI {threshold_method.title()} {threshold:.2f}."
        )
        overlay = composite.copy()
        if show_rings:
            overlay[find_boundaries(rings, mode="inner") & (rings > 0)] = (1, 0, 1)
        if show_nuclei:
            overlay[find_boundaries(nuclei, mode="inner") & (nuclei > 0)] = (1, 1, 1)
        if show_responders:
            responding_labels = np.flatnonzero(responding) + 1
            responders = np.isin(nuclei, responding_labels) & (nuclei > 0)
            overlay[responders] = (1, 1, 0)
        return (np.clip(overlay, 0, 1) * 255).astype(background.dtype)

    def select_well(change: dict[str, Any]) -> None:
        """Update the field slider to the selected well's stored scenes."""
        field_control.options = [
            (f"Field {number + 1} (scene {scene})", scene) for number, scene in enumerate(well_scenes[change["new"]])
        ]

    initial_shape = load_field(well_scenes[initial_well][0])[1].shape
    render_field.__annotations__ = get_type_hints(render_field)
    well_control.observe(select_well, names="value")
    view = stackview.interact(
        render_field,
        np.zeros((*initial_shape, 3), dtype=np.uint8),
        continuous_update=False,
        scene_index=field_control,
        threshold_method=widgets.Dropdown(
            options=[(name.title(), name) for name in THRESHOLD_METHODS],
            value=threshold_method,
            description="Threshold",
        ),
        min_area_px=widgets.IntSlider(
            value=min_nucleus_area_px,
            min=1,
            max=max(400, min_nucleus_area_px * 2),
            description="Min area (px)",
            continuous_update=False,
        ),
        min_distance_px=widgets.IntSlider(
            value=min_nucleus_distance_px,
            min=1,
            max=max(40, min_nucleus_distance_px * 2),
            description="Peak spacing (px)",
            style={"description_width": "initial"},
            tooltip="Minimum spacing between watershed seed peaks, not a gap between nuclei or rings.",
            continuous_update=False,
        ),
        ring_width=widgets.FloatSlider(
            value=configured_width,
            min=min(0.1, configured_width),
            max=max(10.0 if use_microns else 50.0, configured_width * 2),
            step=0.1 if use_microns else 1.0,
            description="Ring (um)" if use_microns else "Ring (px)",
            continuous_update=False,
        ),
        ratio_cutoff=widgets.FloatSlider(
            value=ratio_threshold,
            min=min(0.1, ratio_threshold),
            max=max(10.0, ratio_threshold * 2),
            step=0.1,
            description="Ratio cutoff",
            continuous_update=False,
        ),
    )
    return widgets.VBox([well_control, status, view])


def segment_nuclei(
    dapi: np.ndarray,
    min_area_px: int,
    min_distance_px: int,
    *,
    threshold_method: ThresholdMethod = "otsu",
) -> tuple[np.ndarray, float]:
    """Threshold DAPI and split touching nuclei with distance watershed.

    Args:
        dapi: DAPI intensity plane; non-finite pixels are excluded.
        min_area_px: Minimum retained nucleus area in pixels.
        min_distance_px: Minimum watershed peak separation in pixels.
        threshold_method: Global scikit-image threshold method: otsu, li,
            yen, triangle, isodata, or mean. Otsu preserves the default.

    Returns:
        Sequential int32 nucleus labels and the scalar DAPI threshold.
        Constant images have no foreground; images without finite pixels
        return empty labels and a NaN threshold.

    Raises:
        ValueError: If the threshold method is unsupported.
    """
    threshold_function = THRESHOLD_METHODS.get(threshold_method)
    if threshold_function is None:
        raise ValueError(
            f"Unsupported threshold method {threshold_method!r}; " f"choose from {', '.join(THRESHOLD_METHODS)}."
        )
    image = np.asarray(dapi)
    finite = np.isfinite(image)
    if not finite.any():
        return np.zeros(image.shape, dtype=np.int32), float("nan")

    values = image[finite]
    threshold = float(values[0]) if np.all(values == values[0]) else float(threshold_function(values))
    foreground = finite & (image > threshold)
    foreground = remove_small_objects(foreground, max_size=min_area_px - 1)
    foreground = cast(NDArray[np.bool_], ndi.binary_fill_holes(foreground))
    if not foreground.any():
        return np.zeros(image.shape, dtype=np.int32), threshold

    distance = cast(NDArray[np.float64], ndi.distance_transform_edt(foreground))
    peaks = cast(
        NDArray[np.intp],
        peak_local_max(
            distance,
            min_distance=min_distance_px,
            labels=foreground,
            exclude_border=False,
        ),
    )
    markers = np.zeros(image.shape, dtype=np.int32)
    if peaks.size:
        markers[tuple(peaks.T)] = np.arange(1, len(peaks) + 1)
    else:
        markers, _ = cast(tuple[NDArray[np.int32], int], ndi.label(foreground))

    labels = watershed(-distance, markers, mask=foreground)
    labels = remove_small_objects(labels, max_size=min_area_px - 1)
    labels, _, _ = relabel_sequential(labels)
    return labels.astype(np.int32, copy=False), threshold


def contact_pixels(labels: np.ndarray, neighboring_labels: np.ndarray) -> np.ndarray:
    """Mark pixels adjacent to a differently labeled object in 8-connectivity."""
    height, width = labels.shape
    contacts = np.zeros(labels.shape, dtype=bool)
    for row_offset in (-1, 0, 1):
        for column_offset in (-1, 0, 1):
            if row_offset == 0 and column_offset == 0:
                continue
            source_rows = slice(max(0, -row_offset), min(height, height - row_offset))
            target_rows = slice(max(0, row_offset), min(height, height + row_offset))
            source_columns = slice(max(0, -column_offset), min(width, width - column_offset))
            target_columns = slice(max(0, column_offset), min(width, width + column_offset))
            source = labels[source_rows, source_columns]
            target = neighboring_labels[target_rows, target_columns]
            contacts[source_rows, source_columns] |= (source > 0) & (target > 0) & (source != target)
    return contacts


def make_ring_labels(
    nuclei: np.ndarray,
    ring_width_um: float | None,
    pixel_spacing_um: tuple[float, float],
    ring_width_px: float | None = None,
) -> np.ndarray:
    """Expand labeled nuclei into separate outer rings for EGFP measurement.

    Args:
        nuclei: 2D label image: zero is background, positive integers identify
            individual nuclei.
        ring_width_um: Maximum outward distance in micrometers, or None when
            specifying the width in pixels instead.
        pixel_spacing_um: Physical pixel sizes in (Y, X) order. Used only for
            micrometer distances, including images with unequal X/Y spacing.
        ring_width_px: Maximum outward distance in pixels, or None when
            specifying the width in micrometers instead.

    Returns:
        An int32 image with the same shape as nuclei. Each retained ring pixel
        carries its nucleus's label; nuclei and unassigned pixels are zero.
        Rings may be truncated by other objects or the image boundary.
    """
    # Reject both widths being set or both being None: these are alternative
    # units for one distance, not two independent ring settings.
    if (ring_width_um is None) == (ring_width_px is None):
        raise ValueError("Specify exactly one ring width in microns or pixels.")
    if not np.any(nuclei):
        return np.zeros(nuclei.shape, dtype=np.int32)

    # Physical spacing scales Y/X distances to micrometers. Unit spacing
    # instead measures ordinary Euclidean distance in pixel coordinates.
    if ring_width_um is not None:
        sampling = pixel_spacing_um
        max_distance = ring_width_um
    else:
        assert ring_width_px is not None
        sampling = (1.0, 1.0)
        max_distance = ring_width_px
    # Move the inclusive cutoff one floating-point step upward to tolerate
    # tiny rounding differences for pixels exactly at the requested width.
    max_distance = np.nextafter(float(max_distance), np.inf)

    # SciPy measures each nonzero pixel's distance to the nearest zero pixel.
    # Here background is True (1), and nuclei are False (0), so this finds
    # distance to a nucleus and the (Y, X) coordinates of its nearest pixel.
    distances, nearest_indices = cast(
        tuple[NDArray[np.float64], NDArray[np.int32]],
        ndi.distance_transform_edt(
            nuclei == 0,
            sampling=sampling,
            return_indices=True,
        ),
    )
    # Look up the nucleus ID at those coordinates. Each background pixel gets
    # one candidate owner, even where rings from nearby nuclei would overlap.
    nearest_nuclei = nuclei[tuple(nearest_indices)]

    # Keep only background pixels within the chosen distance of their owner.
    # Nucleus interiors and pixels outside the ring width remain zero.
    ring_labels = np.where(
        (nuclei == 0) & (distances <= max_distance) & (nearest_nuclei > 0),
        nearest_nuclei,
        0,
    ).astype(np.int32, copy=False)

    # Remove ring pixels touching a DIFFERENT nucleus, then pixels touching
    # another ring label. Both checks include diagonal neighbors; contact
    # with the ring's own nucleus is allowed because their labels match.
    ring_labels[contact_pixels(ring_labels, nuclei)] = 0
    ring_labels[contact_pixels(ring_labels, ring_labels)] = 0

    return ring_labels


def measure_scene_objects(
    egfp: np.ndarray,
    nuclei: np.ndarray,
    rings: np.ndarray,
    pixel_spacing_um: tuple[float, float],
    well_name: str,
    scene_index: int,
    dapi_threshold: float,
) -> list[dict[str, Any]]:
    """Measure EGFP intensity and area for each nucleus and assigned ring."""
    if egfp.shape != nuclei.shape or nuclei.shape != rings.shape:
        raise ValueError("EGFP, nucleus, and ring arrays must have matching shapes.")

    object_count = int(nuclei.max())
    if not object_count:
        return []

    # Compute areas and sums for nuclei and rings.
    nucleus_areas = np.bincount(nuclei.ravel(), minlength=object_count + 1)
    nucleus_sums = np.bincount(nuclei.ravel(), weights=egfp.ravel(), minlength=object_count + 1)
    ring_areas = np.bincount(rings.ravel(), minlength=object_count + 1)
    ring_sums = np.bincount(rings.ravel(), weights=egfp.ravel(), minlength=object_count + 1)
    pixel_area_um2 = pixel_spacing_um[0] * pixel_spacing_um[1]
    rows: list[dict[str, Any]] = []

    for object_id in range(1, object_count + 1):
        nucleus_area = int(nucleus_areas[object_id])
        ring_area = int(ring_areas[object_id])
        mean_nucleus = float(nucleus_sums[object_id] / nucleus_area)
        mean_ring = float(ring_sums[object_id] / ring_area) if ring_area else float("nan")
        ratio = mean_nucleus / mean_ring if np.isfinite(mean_ring) and mean_ring > 0 else float("nan")
        rows.append(
            {
                "Well": well_name,
                "SceneIndex": scene_index,
                "ObjectID": f"{well_name}_S{scene_index:03d}_N{object_id:04d}",
                "NucleusAreaPx": nucleus_area,
                "NucleusAreaUm2": nucleus_area * pixel_area_um2,
                "RingAreaPx": ring_area,
                "MeanIntNuc": mean_nucleus,
                "MeanIntRing": mean_ring,
                "TranslocationRatio": ratio,
                "DapiThreshold": dapi_threshold,
            }
        )

    return rows


def finite_mean(values: list[float]) -> float:
    """Return the mean of finite values, or NaN when none are available."""
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]

    return float(np.mean(array)) if array.size else float("nan")


def summarize_wells(
    metadata: CziMetadata | OmeZarrPlate,
    cells_by_well: dict[str, list[dict[str, Any]]],
    scene_indices_by_well: dict[str, list[int]],
    thresholds_by_well: dict[str, list[float]],
    ratio_threshold: float,
    ring_width_um: float | None,
    ring_width_px: float | None,
    plate_layout: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """Create one well-level record for every declared/stored HCS well."""
    if metadata.hcs is None:
        raise ValueError("No HCS plate is available for well summarization.")
    rows: list[dict[str, Any]] = []
    for well in metadata.hcs.wells:
        name = well.canonical_name
        cells = cells_by_well.get(name, [])
        ratios = [float(cell["TranslocationRatio"]) for cell in cells]
        valid_ratios = [value for value in ratios if np.isfinite(value)]
        dose = plate_layout.get(
            name,
            {
                "Drug": "Unassigned",
                "Dose": np.nan,
                "DoseUnit": "",
                "Control": "Blank or unassigned",
            },
        )
        row_name = name.rstrip("0123456789")
        rows.append(
            {
                "Well": name,
                "WellPath": well.canonical_path,
                "Row": row_name,
                "Column": int(name[len(row_name) :]),
                "SceneIndices": ",".join(str(value) for value in sorted(scene_indices_by_well.get(name, []))),
                "FieldCount": len(scene_indices_by_well.get(name, [])),
                "NumberOfObjects": len(cells),
                "MeanIntNuc": finite_mean([float(cell["MeanIntNuc"]) for cell in cells]),
                "MeanIntRing": finite_mean([float(cell["MeanIntRing"]) for cell in cells]),
                "MeanTranslocationRatio": finite_mean(valid_ratios),
                "MedianTranslocationRatio": (float(np.median(valid_ratios)) if valid_ratios else float("nan")),
                "FractionAboveThreshold": (
                    float(np.mean(np.asarray(valid_ratios) >= ratio_threshold)) if valid_ratios else float("nan")
                ),
                "DapiThreshold": finite_mean(thresholds_by_well.get(name, [])),
                "RingWidthUm": ring_width_um,
                "RingWidthPx": ring_width_px,
                **dose,
            }
        )

    return pd.DataFrame(rows)


def dose_response_table(
    cell_table: pd.DataFrame,
    well_table: pd.DataFrame,
    ratio_threshold: float,
) -> pd.DataFrame:
    """Aggregate cells and replicate wells at each supplied drug dose."""

    rows: list[dict[str, Any]] = []
    treatments = well_table[well_table["Control"].eq("") & np.isfinite(well_table["Dose"])]

    for (drug, unit), drug_wells in treatments.groupby(["Drug", "DoseUnit"], sort=False):
        for dose, dose_wells in drug_wells.groupby("Dose", sort=True):
            wells = dose_wells["Well"].tolist()
            cells = cell_table[cell_table["Well"].isin(wells)]
            ratios = pd.to_numeric(cells["TranslocationRatio"], errors="coerce")
            ratios = ratios[np.isfinite(ratios)]
            matching_wells = well_table[well_table["Well"].isin(wells)]
            replicate_fractions = pd.to_numeric(matching_wells["FractionAboveThreshold"], errors="coerce").dropna()
            rows.append(
                {
                    "Drug": drug,
                    "Dose": dose,
                    "DoseUnit": unit,
                    "NumberOfWells": len(wells),
                    "WellsWithObjects": int((matching_wells["NumberOfObjects"] > 0).sum()),
                    "NumberOfCellsWithValidRatio": int(ratios.size),
                    "FractionAboveThreshold": (
                        float((ratios >= ratio_threshold).mean()) if ratios.size else float("nan")
                    ),
                    "MeanWellFractionAboveThreshold": (
                        float(replicate_fractions.mean()) if not replicate_fractions.empty else float("nan")
                    ),
                    "MedianTranslocationRatio": (float(ratios.median()) if ratios.size else float("nan")),
                }
            )
    return pd.DataFrame(rows)


def hill_4pl(
    dose: np.ndarray,
    bottom: float,
    top: float,
    ec50: float,
    hill_slope: float,
) -> np.ndarray:
    """Four-parameter increasing Hill curve."""

    return bottom + (top - bottom) / (1.0 + (ec50 / dose) ** hill_slope)


def fit_hill(
    doses: np.ndarray,
    responses: np.ndarray,
) -> tuple[dict[str, float] | None, str]:
    """Fit a bounded four-parameter Hill curve with a NumPy grid search."""
    valid = np.isfinite(doses) & np.isfinite(responses) & (doses > 0)
    doses = np.asarray(doses[valid], dtype=float)
    responses = np.asarray(responses[valid], dtype=float)

    if doses.size < 4:
        return None, "At least four finite dose responses are required."

    if np.ptp(responses) < 1e-6:
        return None, "Responses are constant; EC50 is not identifiable."

    lower_dose = float(np.min(doses))
    upper_dose = float(np.max(doses))
    responses = np.clip(responses, 0.0, 1.0)

    def search(
        ec50_values: np.ndarray,
        slope_values: np.ndarray,
    ) -> tuple[dict[str, float], float]:
        log_doses = np.log(doses)
        log_ec50 = np.log(ec50_values)[:, None, None]
        slope_grid = slope_values[None, :, None]
        log_ratio = (log_ec50 - log_doses[None, None, :]) * slope_grid
        sigmoid = 1.0 / (1.0 + np.exp(np.clip(log_ratio, -700.0, 700.0)))
        grid_shape = sigmoid.shape[:2]
        mean_response = float(np.mean(responses))
        centered_response = responses - mean_response
        mean_sigmoid = np.mean(sigmoid, axis=2)
        centered_sigmoid = sigmoid - mean_sigmoid[:, :, None]
        variance = np.sum(centered_sigmoid**2, axis=2)
        amplitude = np.divide(
            np.sum(centered_sigmoid * centered_response[None, None, :], axis=2),
            variance,
            out=np.zeros(grid_shape, dtype=float),
            where=variance > 0,
        )
        bottom = mean_response - amplitude * mean_sigmoid
        top = bottom + amplitude
        best_error = np.full(grid_shape, np.inf, dtype=float)
        best_bottom = np.zeros(grid_shape, dtype=float)
        best_top = np.zeros(grid_shape, dtype=float)

        def consider(
            candidate_bottom: np.ndarray,
            candidate_top: np.ndarray,
            allowed: np.ndarray,
        ) -> None:
            prediction = candidate_bottom[:, :, None] + (candidate_top - candidate_bottom)[:, :, None] * sigmoid
            errors = np.sum((prediction - responses[None, None, :]) ** 2, axis=2)
            errors = np.where(allowed, errors, np.inf)
            improved = errors < best_error
            best_error[improved] = errors[improved]
            best_bottom[improved] = candidate_bottom[improved]
            best_top[improved] = candidate_top[improved]

        interior = np.isfinite(bottom) & np.isfinite(top) & (amplitude >= 0.0) & (bottom >= 0.0) & (top <= 1.0)
        consider(bottom, top, interior)

        sigmoid_squared = np.sum(sigmoid**2, axis=2)
        lower_amplitude = np.divide(
            np.sum(sigmoid * responses[None, None, :], axis=2),
            sigmoid_squared,
            out=np.zeros(grid_shape, dtype=float),
            where=sigmoid_squared > 0,
        )
        lower_amplitude = np.clip(lower_amplitude, 0.0, 1.0)
        consider(
            np.zeros(grid_shape),
            lower_amplitude,
            np.ones(grid_shape, dtype=bool),
        )

        inverse = 1.0 - sigmoid
        inverse_squared = np.sum(inverse**2, axis=2)
        upper_amplitude = np.divide(
            np.sum(inverse * (1.0 - responses)[None, None, :], axis=2),
            inverse_squared,
            out=np.zeros(grid_shape, dtype=float),
            where=inverse_squared > 0,
        )
        upper_amplitude = np.clip(upper_amplitude, 0.0, 1.0)
        consider(
            1.0 - upper_amplitude,
            np.ones(grid_shape),
            np.ones(grid_shape, dtype=bool),
        )

        constant = np.full(grid_shape, mean_response, dtype=float)
        consider(constant, constant, np.ones(grid_shape, dtype=bool))
        best_index = np.unravel_index(np.argmin(best_error), best_error.shape)
        ec50_index, slope_index = best_index
        parameters = {
            "Bottom": float(best_bottom[best_index]),
            "Top": float(best_top[best_index]),
            "EC50": float(ec50_values[ec50_index]),
            "HillSlope": float(slope_values[slope_index]),
        }
        return parameters, float(best_error[best_index])

    min_ec50 = lower_dose / 100.0
    max_ec50 = upper_dose * 100.0
    fit, error = search(
        np.geomspace(min_ec50, max_ec50, 301),
        np.linspace(0.05, 5.0, 121),
    )
    for log_span, slope_span in ((0.15, 0.5), (0.03, 0.1)):
        ec50_values = np.geomspace(
            max(min_ec50, fit["EC50"] / (10.0**log_span)),
            min(max_ec50, fit["EC50"] * (10.0**log_span)),
            101,
        )
        slope_values = np.linspace(
            max(0.05, fit["HillSlope"] - slope_span),
            min(5.0, fit["HillSlope"] + slope_span),
            101,
        )
        fit, error = search(ec50_values, slope_values)

    if fit["Top"] - fit["Bottom"] < 1e-6:
        return None, "Fitted response does not increase with dose."
    fit["RMSE"] = float(np.sqrt(error / doses.size))
    return fit, "Fit successful (bounded NumPy grid search)."


def analyze_scenes(
    metadata: CziMetadata | OmeZarrPlate,
    scene_arrays: list[Any] | None,
    scene_wells: dict[int, str],
    channel_indices: dict[str, int],
    pixel_spacing_um: tuple[float, float],
    dimensions: Any,
    min_nucleus_area_px: int,
    min_nucleus_distance_px: int,
    ratio_threshold: float,
    ring_width_um: float | None,
    ring_width_px: float | None,
    plate_layout: dict[str, dict[str, Any]],
    segmentation_scene: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    field_reader: Callable[[int], Any] | None = None,
    threshold_method: ThresholdMethod = "otsu",
) -> AssayResults:
    """Analyze scene arrays or load mapped fields on demand via field_reader.

    Pass exactly one of scene_arrays and field_reader; the other must be None.
    The callback accepts a stored scene index, not a well-local field index.
    threshold_method selects the global DAPI threshold for every field;
    cleanup, watershed splitting, and EGFP measurements remain unchanged.
    """
    if threshold_method not in THRESHOLD_METHODS:
        raise ValueError(f"Unsupported threshold method: {threshold_method}")
    if metadata.hcs is None:
        raise ValueError("No HCS plate is available for analysis.")
    if (scene_arrays is None) == (field_reader is None):
        raise ValueError("Provide exactly one of scene_arrays or field_reader.")
    scene_indices = list(range(len(scene_arrays))) if scene_arrays is not None else sorted(scene_wells)
    scene_count = len(scene_indices)
    if segmentation_scene is not None and (
        segmentation_scene not in scene_indices or segmentation_scene not in scene_wells
    ):
        raise ValueError(
            f"Segmentation scene {segmentation_scene} is unavailable or has no well assignment; "
            "choose a mapped zero-based stored scene index."
        )
    egfp_index = channel_indices["EGFP"]
    dapi_index = channel_indices["DAPI"]
    cells_by_well: dict[str, list[dict[str, Any]]] = {well.canonical_name: [] for well in metadata.hcs.wells}
    scene_indices_by_well = {name: [] for name in cells_by_well}
    thresholds_by_well = {name: [] for name in cells_by_well}
    cell_rows: list[dict[str, Any]] = []
    segmentation_example = None

    for completed, scene_index in enumerate(scene_indices, start=1):
        well_name = scene_wells.get(scene_index)
        if well_name is None:
            if progress_callback is not None:
                progress_callback(completed, scene_count)
            continue
        # Both readers enter the same processing path. The callback reads one
        # HCS field now; the array path computes its lazy scene below.
        if field_reader is not None:
            scene_array = field_reader(scene_index)
        else:
            assert scene_arrays is not None
            scene_array = scene_arrays[scene_index]
        if scene_array.sizes.get("C", 0) <= max(egfp_index, dapi_index):
            raise ValueError(f"Scene {scene_index} does not contain both assay channels.")

        field = scene_array.compute() if hasattr(scene_array.data, "compute") else scene_array
        egfp = np.asarray(
            field.isel(C=egfp_index).squeeze(drop=True).values,
            dtype=np.float64,
        )
        dapi = np.asarray(
            field.isel(C=dapi_index).squeeze(drop=True).values,
            dtype=np.float64,
        )
        if egfp.ndim != 2 or dapi.ndim != 2 or egfp.shape != dapi.shape:
            raise ValueError(
                f"Expected matching 2D channel planes in scene {scene_index}; "
                f"got EGFP {egfp.shape} and DAPI {dapi.shape} "
                f"(axes {dimensions})."
            )

        nuclei, dapi_threshold = segment_nuclei(
            dapi,
            min_area_px=min_nucleus_area_px,
            min_distance_px=min_nucleus_distance_px,
            threshold_method=threshold_method,
        )
        rings = make_ring_labels(
            nuclei,
            ring_width_um,
            pixel_spacing_um,
            ring_width_px,
        )
        thresholds_by_well[well_name].append(dapi_threshold)
        scene_indices_by_well[well_name].append(scene_index)
        if scene_index == segmentation_scene or (
            segmentation_scene is None and nuclei.any() and segmentation_example is None
        ):
            channel_info = metadata.channelinfo
            if channel_info is None:
                raise ValueError("Channel metadata are unavailable for the segmentation preview.")
            segmentation_example = (
                dapi.copy(),
                nuclei.copy(),
                rings.copy(),
                well_name,
                scene_index,
                dapi_threshold,
                _channel_composite(
                    [egfp, dapi],
                    [channel_info.colors[index] for index in (egfp_index, dapi_index)],
                ),
            )
        scene_rows = measure_scene_objects(
            egfp,
            nuclei,
            rings,
            pixel_spacing_um,
            well_name,
            scene_index,
            dapi_threshold,
        )
        cell_rows.extend(scene_rows)
        cells_by_well[well_name].extend(scene_rows)
        if progress_callback is not None:
            progress_callback(completed, scene_count)
        elif completed % 12 == 0 or completed == scene_count:
            LOGGER.info("Processed %d/%d fields", completed, scene_count)

    cell_columns = [
        "Well",
        "SceneIndex",
        "ObjectID",
        "NucleusAreaPx",
        "NucleusAreaUm2",
        "RingAreaPx",
        "MeanIntNuc",
        "MeanIntRing",
        "TranslocationRatio",
        "DapiThreshold",
    ]
    cell_table = pd.DataFrame(cell_rows, columns=cell_columns)
    well_table = summarize_wells(
        metadata,
        cells_by_well,
        scene_indices_by_well,
        thresholds_by_well,
        ratio_threshold,
        ring_width_um,
        ring_width_px,
        plate_layout,
    )
    dose_table = dose_response_table(cell_table, well_table, ratio_threshold)

    fits: dict[str, tuple[dict[str, float] | None, str]] = {}
    ec50_rows: list[dict[str, Any]] = []
    for (drug, unit), data in dose_table.groupby(["Drug", "DoseUnit"], sort=False):
        fit, message = fit_hill(
            data["Dose"].to_numpy(dtype=float),
            data["FractionAboveThreshold"].to_numpy(dtype=float),
        )
        fits[str(drug)] = (fit, message)
        ec50_rows.append(
            {
                "Drug": drug,
                "DoseUnit": unit,
                "EC50": fit["EC50"] if fit else np.nan,
                "Bottom": fit["Bottom"] if fit else np.nan,
                "Top": fit["Top"] if fit else np.nan,
                "HillSlope": fit["HillSlope"] if fit else np.nan,
                "RMSE": fit["RMSE"] if fit else np.nan,
                "FitStatus": "success" if fit else "unavailable",
                "FitMessage": message,
            }
        )

    return AssayResults(
        cell_table=cell_table,
        well_table=well_table,
        dose_table=dose_table,
        fits=fits,
        ec50_table=pd.DataFrame(ec50_rows),
        segmentation_example=segmentation_example,
        fields_processed=sum(len(indices) for indices in scene_indices_by_well.values()),
    )


def _plate_values(well_table: pd.DataFrame, column: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for well_path, value in zip(well_table["WellPath"], well_table[column], strict=True):
        values[str(well_path)] = float(value) if pd.notna(value) else float("nan")
    return values


def _save_heatmaps_plotly(well_table: pd.DataFrame, output_dir: Path) -> None:
    import plotly.graph_objects as go

    heatmaps = (
        ("NumberOfObjects", "Objects per well", "Number of objects", ".0f", "heatmap_number_of_objects.html"),
        (
            "MedianTranslocationRatio",
            "Median EGFP nucleus/ring ratio per well",
            "TranslocationRatio",
            ".2f",
            "heatmap_translocation_ratio.html",
        ),
    )
    rows = list("ABCDEFGH")
    columns = list(range(1, 13))
    for column, title, parameter, number_format, filename in heatmaps:
        values = _plate_values(well_table, column)
        matrix = [[values.get(f"{row}/{col}", float("nan")) for col in columns] for row in rows]
        annotations = [
            ["" if not np.isfinite(value) else f"{value:{number_format}}" for value in row] for row in matrix
        ]
        figure = go.Figure(
            data=go.Heatmap(
                z=matrix,
                x=columns,
                y=rows,
                text=annotations,
                texttemplate="%{text}",
                colorscale="Viridis",
                colorbar={"title": parameter},
                hovertemplate=f"Well %{{y}}%{{x}}<br>{parameter}: %{{z}}<extra></extra>",
            )
        )
        figure.update_layout(
            title=title,
            xaxis_title="Column",
            yaxis_title="Row",
            yaxis_autorange="reversed",
            width=1200,
            height=650,
        )
        figure.write_html(output_dir / filename, include_plotlyjs="directory", auto_open=False)


def _save_heatmaps_seaborn(well_table: pd.DataFrame, output_dir: Path) -> None:
    import matplotlib.pyplot as plt

    from czitools.analysis_tools.plotting import create_well_plate_heatmap

    heatmaps = (
        ("NumberOfObjects", "Objects per well", "Number of objects", ".0f", "heatmap_number_of_objects.png"),
        (
            "MedianTranslocationRatio",
            "Median EGFP nucleus/ring ratio per well",
            "TranslocationRatio",
            ".2f",
            "heatmap_translocation_ratio.png",
        ),
    )
    for column, title, parameter, number_format, filename in heatmaps:
        figure = create_well_plate_heatmap(
            _plate_values(well_table, column),
            num_rows=8,
            num_cols=12,
            title=title,
            parameter=parameter,
            cmap="viridis",
            figsize=(12, 6),
            annot=True,
            fmt=number_format,
        )
        figure.savefig(output_dir / filename, dpi=180, bbox_inches="tight")
        plt.close(figure)


def save_heatmaps(
    well_table: pd.DataFrame,
    output_dir: Path,
    backend: PlotBackend,
) -> None:
    """Write well-plate heatmaps using the selected visualization backend."""
    if backend == "plotly":
        _save_heatmaps_plotly(well_table, output_dir)
    elif backend == "seaborn":
        _save_heatmaps_seaborn(well_table, output_dir)
    else:
        raise ValueError(f"Unsupported plot backend: {backend}")


def _segmentation_edges(
    nuclei: np.ndarray,
    rings: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    structure = np.ones((3, 3), dtype=bool)
    nucleus_mask = nuclei > 0
    ring_mask = rings > 0
    dilated_nucleus_background = cast(NDArray[np.bool_], ndi.binary_dilation(~nucleus_mask, structure=structure))
    dilated_ring_background = cast(NDArray[np.bool_], ndi.binary_dilation(~ring_mask, structure=structure))
    nucleus_edges = (nucleus_mask & dilated_nucleus_background) | contact_pixels(nuclei, nuclei)
    ring_edges = (ring_mask & dilated_ring_background) | contact_pixels(rings, rings)
    return nucleus_edges, ring_edges


def _channel_composite(images: list[np.ndarray], colors: list[str]) -> np.ndarray:
    """Color channels with microfilm using CZI ARGB colors and black minima."""
    from matplotlib.colors import LinearSegmentedColormap
    from microfilm.colorify import multichannel_to_rgb

    if len(images) != len(colors):
        raise ValueError("Each channel must have one CZI display color.")
    colormaps = []
    limits = []
    cleaned = []
    for index, (image, color) in enumerate(zip(images, colors, strict=True)):
        rgb = color.removeprefix("#")
        if len(rgb) == 8:
            rgb = rgb[2:]
        if len(rgb) != 6:
            raise ValueError(f"Invalid CZI channel color: {color!r}")
        colormaps.append(LinearSegmentedColormap.from_list(f"channel_{index}", ["black", f"#{rgb}"]))
        finite = image[np.isfinite(image)]
        low, high = np.percentile(finite, (1, 99.5)) if finite.size else (0.0, 1.0)
        if high <= low:
            low, high = 0.0, max(float(high), 1.0)
        limits.append([float(low), float(high)])
        cleaned.append(np.where(np.isfinite(image), image, low))
    composite, _, _, _ = multichannel_to_rgb(
        cleaned,
        cmaps=colormaps,
        rescale_type="limits",
        limits=limits,
        proj_type="sum",
    )
    return np.rint(np.clip(composite[:, :, :3], 0.0, 1.0) * 255).astype(np.uint8)


def save_segmentation_example(
    dapi: np.ndarray,
    nuclei: np.ndarray,
    rings: np.ndarray,
    well_name: str,
    scene_index: int,
    dapi_threshold: float,
    composite: np.ndarray,
    ring_width_label: str,
    output_dir: Path,
    backend: PlotBackend,
) -> None:
    """Save a microfilm channel composite and its segmentation overlay."""
    valid = dapi[np.isfinite(dapi)]
    if not valid.size:
        LOGGER.warning("Skipping segmentation example because DAPI is empty")
        return
    nucleus_edges, ring_edges = _segmentation_edges(nuclei, rings)

    if backend == "plotly":
        _save_segmentation_plotly(
            composite,
            nuclei,
            rings,
            nucleus_edges,
            ring_edges,
            well_name,
            scene_index,
            dapi_threshold,
            ring_width_label,
            output_dir,
        )
    elif backend == "seaborn":
        _save_segmentation_seaborn(
            composite,
            nuclei,
            rings,
            well_name,
            scene_index,
            dapi_threshold,
            ring_width_label,
            output_dir,
        )
    else:
        raise ValueError(f"Unsupported plot backend: {backend}")


def _save_segmentation_plotly(
    composite: np.ndarray,
    nuclei: np.ndarray,
    rings: np.ndarray,
    nucleus_edges: np.ndarray,
    ring_edges: np.ndarray,
    well_name: str,
    scene_index: int,
    dapi_threshold: float,
    ring_width_label: str,
    output_dir: Path,
) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    figure = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("EGFP + DAPI", "Nucleus and ring segmentation"),
    )
    for column in (1, 2):
        figure.add_trace(
            go.Image(
                z=composite,
                hoverinfo="skip",
            ),
            row=1,
            col=column,
        )
    figure.add_trace(
        go.Heatmap(
            z=np.where(rings > 0, 1.0, np.nan),
            colorscale=[[0, "rgba(255, 145, 0, 0.55)"], [1, "rgba(255, 145, 0, 0.55)"]],
            zmin=0,
            zmax=1,
            showscale=False,
            hoverinfo="skip",
            name="Ring area",
        ),
        row=1,
        col=2,
    )
    figure.add_trace(
        go.Heatmap(
            z=np.where(nuclei > 0, 1.0, np.nan),
            colorscale=[[0, "rgba(0, 220, 255, 0.65)"], [1, "rgba(0, 220, 255, 0.65)"]],
            zmin=0,
            zmax=1,
            showscale=False,
            hoverinfo="skip",
            name="Nucleus area",
        ),
        row=1,
        col=2,
    )
    for mask, color, name in (
        (ring_edges, "#ff9100", "Ring boundary"),
        (nucleus_edges, "#00dcff", "Nucleus boundary"),
    ):
        rows, columns = np.nonzero(mask)
        figure.add_trace(
            go.Scattergl(
                x=columns,
                y=rows,
                mode="markers",
                marker={"color": color, "size": 2},
                name=name,
                hoverinfo="skip",
            ),
            row=1,
            col=2,
        )
    height, width = nuclei.shape
    figure.update_xaxes(
        range=[-0.5, width - 0.5],
        autorange=False,
        showticklabels=False,
        showgrid=False,
        zeroline=False,
        constrain="domain",
    )
    figure.update_yaxes(
        range=[height - 0.5, -0.5],
        autorange=False,
        showticklabels=False,
        showgrid=False,
        zeroline=False,
        constrain="domain",
    )
    figure.update_yaxes(scaleanchor="x", scaleratio=1, row=1, col=1)
    figure.update_yaxes(scaleanchor="x2", scaleratio=1, row=1, col=2)
    figure.update_layout(
        title=(
            f"Segmentation example: well {well_name}, scene {scene_index}"
            f"<br><sup>{int(nuclei.max())} nuclei; DAPI threshold "
            f"{dapi_threshold:.3g}; ring width {ring_width_label}</sup>"
        ),
        width=1250,
        height=700,
        paper_bgcolor="black",
        plot_bgcolor="black",
        font={"color": "white"},
        margin={"t": 105, "b": 35},
        legend={"orientation": "h", "y": -0.08},
    )
    figure.write_html(
        output_dir / "segmentation_example.html",
        include_plotlyjs="directory",
        auto_open=False,
    )


def _save_segmentation_seaborn(
    composite: np.ndarray,
    nuclei: np.ndarray,
    rings: np.ndarray,
    well_name: str,
    scene_index: int,
    dapi_threshold: float,
    ring_width_label: str,
    output_dir: Path,
) -> None:
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(12, 6), constrained_layout=True, facecolor="black")
    for axis in axes:
        axis.imshow(composite, interpolation="nearest")
        axis.set_facecolor("black")
        axis.set_axis_off()
        axis.set_aspect("equal")
    axes[0].set_title("EGFP + DAPI", color="white")
    axes[1].contour(rings > 0, levels=[0.5], colors=["#ff9100"], linewidths=0.7)
    axes[1].contour(nuclei > 0, levels=[0.5], colors=["#00a9c7"], linewidths=0.8)
    axes[1].set_title("Nucleus and ring segmentation", color="white")
    figure.suptitle(
        f"Segmentation example: well {well_name}, scene {scene_index}\n"
        f"{int(nuclei.max())} nuclei; DAPI threshold {dapi_threshold:.3g}; "
        f"ring width {ring_width_label}",
        color="white",
    )
    figure.savefig(output_dir / "segmentation_example.png", dpi=180, bbox_inches="tight")
    plt.close(figure)


def _normalized_responses(
    responses: np.ndarray,
    fit: dict[str, float] | None,
) -> np.ndarray:
    finite = np.isfinite(responses)
    normalized = np.full(responses.shape, np.nan)
    if fit is not None and fit["Top"] > fit["Bottom"]:
        normalized[finite] = np.clip(
            (responses[finite] - fit["Bottom"]) / (fit["Top"] - fit["Bottom"]),
            0.0,
            1.0,
        )
    elif finite.any() and np.ptp(responses[finite]) > 0:
        normalized[finite] = (responses[finite] - np.min(responses[finite])) / np.ptp(responses[finite])
    return normalized


def save_dose_response_plot(
    dose_table: pd.DataFrame,
    fits: dict[str, tuple[dict[str, float] | None, str]],
    output_dir: Path,
    backend: PlotBackend,
) -> None:
    """Write dose-response panels on log axes with ticks at measured doses."""
    if backend == "plotly":
        _save_dose_response_plotly(dose_table, fits, output_dir)
    elif backend == "seaborn":
        _save_dose_response_seaborn(dose_table, fits, output_dir)
    else:
        raise ValueError(f"Unsupported plot backend: {backend}")


def _save_dose_response_plotly(
    dose_table: pd.DataFrame,
    fits: dict[str, tuple[dict[str, float] | None, str]],
    output_dir: Path,
) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    groups = list(dose_table.groupby(["Drug", "DoseUnit"], sort=False))
    if not groups:
        LOGGER.warning("No dose-response groups; skipping dose-response plot")
        return
    figure = make_subplots(
        rows=len(groups),
        cols=2,
        subplot_titles=[
            title
            for (drug, _unit), _data in groups
            for title in (f"Dose-Response {drug}", f"Dose-Response {drug} (normalized)")
        ],
        vertical_spacing=min(0.17, 0.5 / len(groups)),
        horizontal_spacing=0.12,
    )
    for row, ((drug, unit), data) in enumerate(groups, start=1):
        data = data.sort_values("Dose")
        doses = data["Dose"].to_numpy(dtype=float)
        responses = data["FractionAboveThreshold"].to_numpy(dtype=float)
        fit, message = fits[str(drug)]
        normalized = _normalized_responses(responses, fit)
        figure.add_trace(
            go.Scatter(
                x=doses,
                customdata=doses,
                y=responses,
                mode="markers+lines",
                marker={"color": "#1976bd", "size": 8},
                line={"color": "#1976bd", "width": 2},
                hovertemplate=(f"{drug}<br>Dose: %{{customdata:g}} {unit}<br>" "Fraction: %{y:.3f}<extra></extra>"),
                showlegend=False,
            ),
            row=row,
            col=1,
        )
        if fit is not None:
            fit_doses = np.geomspace(float(doses.min()), float(doses.max()), 250)
            fit_response = hill_4pl(
                fit_doses,
                fit["Bottom"],
                fit["Top"],
                fit["EC50"],
                fit["HillSlope"],
            )
            figure.add_trace(
                go.Scatter(
                    x=doses,
                    customdata=doses,
                    y=normalized,
                    mode="markers+lines",
                    marker={"color": "#111111", "size": 8},
                    line={"color": "#111111", "width": 2},
                    showlegend=False,
                ),
                row=row,
                col=2,
            )
            figure.add_trace(
                go.Scatter(
                    x=fit_doses,
                    customdata=fit_doses,
                    y=(fit_response - fit["Bottom"]) / (fit["Top"] - fit["Bottom"]),
                    mode="lines",
                    line={"color": "#e32219", "width": 2},
                    showlegend=False,
                ),
                row=row,
                col=2,
            )
            figure.add_shape(
                type="line",
                xref="x domain",
                x0=0,
                x1=1,
                y0=0.5,
                y1=0.5,
                line={"color": "#e32219", "dash": "dash", "width": 1.5},
                row=row,
                col=2,
            )
            label_dose = max(
                float(doses[1]),
                min(fit["EC50"] * 2.5, float(doses[-1]) * 0.8),
            )
            figure.add_annotation(
                x=float(np.log10(label_dose)),
                y=0.08,
                text=f"<b>EC50 = {fit['EC50']:.3g} {unit}</b>",
                showarrow=False,
                font={"color": "#e32219", "size": 18},
                row=row,
                col=2,
            )
        else:
            if np.isfinite(normalized).any():
                figure.add_trace(
                    go.Scatter(
                        x=doses,
                        customdata=doses,
                        y=normalized,
                        mode="markers+lines",
                        marker={"color": "#111111", "size": 8},
                        line={"color": "#111111", "width": 2},
                        showlegend=False,
                    ),
                    row=row,
                    col=2,
                )
            figure.add_annotation(
                text=f"EC50 unavailable: {message}",
                xref="x domain",
                yref="y domain",
                x=0.5,
                y=0.95,
                showarrow=False,
                font={"color": "#e32219", "size": 12},
                row=row,
                col=2,
            )
        for column in (1, 2):
            figure.update_xaxes(
                type="log",
                tickmode="array",
                tickvals=doses,
                ticktext=[f"{dose:g}" for dose in doses],
                range=[float(np.log10(doses.min())), float(np.log10(doses.max()))],
                title_text=f"Dose ({unit})",
                showgrid=True,
                row=row,
                col=column,
            )
            figure.update_yaxes(range=[-0.05, 1.05], showgrid=True, row=row, col=column)
        figure.update_yaxes(
            title_text="Fraction of cells with TranslocationRatio >= 2.0",
            row=row,
            col=1,
        )
        figure.update_yaxes(title_text="Normalized fraction (response)", row=row, col=2)
    figure.update_layout(
        title="Dose-response curves and EC50 fits",
        width=1200,
        height=400 * len(groups),
        hovermode="closest",
        margin={"t": 100, "b": 55, "l": 90, "r": 35},
    )
    figure.write_html(
        output_dir / "dose_response_ec50.html",
        include_plotlyjs="directory",
        auto_open=False,
    )


def _save_dose_response_seaborn(
    dose_table: pd.DataFrame,
    fits: dict[str, tuple[dict[str, float] | None, str]],
    output_dir: Path,
) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    groups = list(dose_table.groupby(["Drug", "DoseUnit"], sort=False))
    if not groups:
        LOGGER.warning("No dose-response groups; skipping dose-response plot")
        return
    figure, axes = plt.subplots(
        len(groups),
        2,
        figsize=(12, 4 * len(groups)),
        constrained_layout=True,
        squeeze=False,
    )
    for row, ((drug, unit), data) in enumerate(groups):
        data = data.sort_values("Dose")
        doses = data["Dose"].to_numpy(dtype=float)
        responses = data["FractionAboveThreshold"].to_numpy(dtype=float)
        fit, message = fits[str(drug)]
        normalized = _normalized_responses(responses, fit)
        raw_axis, normalized_axis = axes[row]
        sns.lineplot(
            x=doses,
            y=responses,
            marker="o",
            errorbar=None,
            color="#1976bd",
            ax=raw_axis,
        )
        sns.lineplot(
            x=doses,
            y=normalized,
            marker="o",
            errorbar=None,
            color="#111111",
            ax=normalized_axis,
        )
        if fit is not None:
            fit_doses = np.geomspace(float(doses.min()), float(doses.max()), 250)
            fit_response = hill_4pl(
                fit_doses,
                fit["Bottom"],
                fit["Top"],
                fit["EC50"],
                fit["HillSlope"],
            )
            sns.lineplot(
                x=fit_doses,
                y=(fit_response - fit["Bottom"]) / (fit["Top"] - fit["Bottom"]),
                color="#e32219",
                ax=normalized_axis,
            )
            normalized_axis.axhline(0.5, color="#e32219", linestyle="--")
            normalized_axis.text(
                0.04,
                0.08,
                f"EC50 = {fit['EC50']:.3g} {unit}",
                color="#e32219",
                transform=normalized_axis.transAxes,
            )
        else:
            normalized_axis.text(
                0.04,
                0.92,
                f"EC50 unavailable: {message}",
                color="#e32219",
                transform=normalized_axis.transAxes,
                va="top",
            )
        for axis in (raw_axis, normalized_axis):
            axis.set_xscale("log")
            axis.set_xticks(doses, labels=[f"{dose:g}" for dose in doses])
            axis.minorticks_off()
            axis.set_ylim(-0.05, 1.05)
            axis.set_xlabel(f"Dose ({unit})")
            axis.grid(True, alpha=0.3)
        raw_axis.set_title(f"Dose-response {drug}")
        raw_axis.set_ylabel("Fraction above threshold")
        normalized_axis.set_title(f"Dose-response {drug} (normalized)")
        normalized_axis.set_ylabel("Normalized fraction (response)")
    figure.suptitle("Dose-response curves and EC50 fits")
    figure.savefig(output_dir / "dose_response_ec50.png", dpi=180, bbox_inches="tight")
    plt.close(figure)


def write_analysis_outputs(
    results: AssayResults,
    output_dir: Path,
    parameters: dict[str, Any],
    plot_backend: PlotBackend,
) -> None:
    """Write result tables, selected plots, and analysis parameters."""
    LOGGER.info("Writing result tables to %s", output_dir)
    results.cell_table.to_csv(output_dir / "cell_measurements.csv", index=False)
    results.well_table.to_csv(output_dir / "well_summary.csv", index=False)
    results.dose_table.to_csv(output_dir / "dose_response_summary.csv", index=False)
    results.ec50_table.to_csv(output_dir / "ec50_results.csv", index=False)

    LOGGER.info("Writing plate heatmaps with %s", plot_backend)
    save_heatmaps(results.well_table, output_dir, plot_backend)
    if results.segmentation_example is not None:
        LOGGER.info("Writing example nucleus/ring segmentation plot")
        save_segmentation_example(
            *results.segmentation_example,
            parameters["RingWidthLabel"],
            output_dir,
            plot_backend,
        )
    else:
        LOGGER.warning("No nuclei were segmented; skipping segmentation example plot")
    LOGGER.info("Writing dose-response plot")
    save_dose_response_plot(
        results.dose_table,
        results.fits,
        output_dir,
        plot_backend,
    )

    with (output_dir / "analysis_parameters.json").open("w", encoding="utf-8") as stream:
        json.dump(parameters, stream, indent=2)

    LOGGER.info(
        "Detected %d nuclei across %d wells",
        len(results.cell_table),
        len(results.well_table),
    )
    LOGGER.info("Wrote assay tables and plots to %s", output_dir)
    for row in results.ec50_table.to_dict(orient="records"):
        if row["FitStatus"] == "success":
            LOGGER.info(
                "%s EC50: %.4g %s",
                row["Drug"],
                row["EC50"],
                row["DoseUnit"],
            )
        else:
            LOGGER.warning("%s EC50 unavailable: %s", row["Drug"], row["FitMessage"])
