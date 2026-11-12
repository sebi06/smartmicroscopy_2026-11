# CZI Handling Examples

Read CZI metadata and pixels, explore well plates, display images, and export
XML, OME-Zarr, or reference-backed VZIP archives.

## Setup and Running

Run terminal commands from the **workshop root**, the folder containing
[pixi.toml](../../pixi.toml):

```powershell
pixi install --locked
pixi run --locked python examples\czi_handling\use_read_tools.py
```

`pixi run` activates the workshop environment even if the terminal shows
Conda `(base)`. Selecting an interpreter in VS Code does not activate an
existing terminal. Alternatively, enter `pixi shell`, run `python` commands,
and leave with `exit`. No separate `pip install` is needed for these examples.

For notebooks, select the workshop's default Pixi kernel and run cells in
order. Start from the root or a subdirectory; [workshop_utils.py](../../workshop_utils.py)
finds the root from `pixi.toml` and sets up example/data/model paths.
File-chooser examples require selecting and confirming a file before reading.
GUI viewers require a graphical desktop.

## Notebooks

| Notebook | Purpose |
| --- | --- |
| [read_czi_metadata.ipynb](read_czi_metadata.ipynb) | Dimensions, channels, scaling, instrument/sample metadata, XML and planetable export. |
| [read_czi_pixeldata_simple.ipynb](read_czi_pixeldata_simple.ipynb) | Introductory pixel reading and Napari display. |
| [read_czi_pixeldata.ipynb](read_czi_pixeldata.ipynb) | Multidimensional pixel arrays, Napari display, and stack reading. |
| [read_czi_wellplate_data.ipynb](read_czi_wellplate_data.ipynb) | Plate/well/field hierarchy, field reads, positions, and planetable enrichment. |
| [using_pylibCZIrw.ipynb](using_pylibCZIrw.ipynb) | Lower-level CZI reading/writing, ROIs, scenes, compression, metadata, and tiling. |
| [czitools_usage_demo.ipynb](czitools_usage_demo.ipynb) | API overview: metadata, reader choices, HCS, and OME-Zarr export. Adjust its developer-specific input path. |

Suggested order: metadata -> simple pixel reading -> full pixel reading ->
well plates; use the low-level tutorial when implementing CZI writing.

## Scripts

Run scripts with `pixi run --locked python examples\czi_handling\<script>.py`.
Unless noted, select the input in the file dialog.

| Script | Purpose / input |
| --- | --- |
| [use_metadata_tools.py](use_metadata_tools.py) | Inspect grouped metadata and export XML. |
| [export_xml_from_czi.py](export_xml_from_czi.py) | Export the selected CZI's metadata XML. |
| [read_planetable.py](read_planetable.py) | Inspect plane metadata and save a planetable. |
| [use_read_tools.py](use_read_tools.py) | Read a selected STCZYX subset and show it in Napari. |
| [read_mdstack.py](read_mdstack.py) | Lazy, scene-aware stack reading and Napari display; defaults to `WP96_4Pos_B4-10_DAPI.czi`. |
| [use_ndv.py](use_ndv.py) | File picker, lazy stack reading, and NDV display; viewer/reader flags are near the top. |
| [read_attachment_images.py](read_attachment_images.py) | Read slide-preview, label, and prescan attachments; adjust its relative `filepath` first. |
| [run_omezarr_gui.py](run_omezarr_gui.py) | Interactive CZI-to-OME-Zarr converter; shortcut: `pixi run omezarr-gui`. |
| [create_czi_vzip.py](create_czi_vzip.py) | Create a reference archive; accepts a source CZI, `-o`, and `--overwrite`. |
| [view_czi_vzip_napari.py](view_czi_vzip_napari.py) | Open an existing VZIP lazily in Napari without recreating it. |

### VZIP Round Trip

```powershell
pixi run --locked python examples\czi_handling\create_czi_vzip.py "data\RatBrain_Z79_ZSTD.czi" -o "results\brain.vzip"
pixi run --locked python examples\czi_handling\view_czi_vzip_napari.py "results\brain.vzip"
```

The output directory must exist. Use `--help` for CLI details and
`--overwrite` only when replacement is intended. **VZIP is not a standalone
image:** keep the original CZI unchanged at the referenced location.

## Data and Output Notes

- Obtain inputs under [data/](../../data/). Well-plate examples use
  `WP96_4Pos_B4-10_DAPI.czi`; the low-level writing tutorial also needs
  `C=1_Z=76_Y=200_X=225_volume.npy`. Check each example's parameters.
- `read_6darray` provides regular arrays; `read_stacks(use_dask=True)` reads
  planes on demand and may return a list when scenes cannot be stacked.
- XML/CSV exports can be written beside the source. Writing tutorials create
  new CZI files and include overwrite examples: review destinations first.
- [screenshots/](screenshots/) contains tutorial illustrations. Generated data
  is not source code; prefer [results/](../../results/) for new exports.
