# Translocation Assay

This example measures nuclear-to-cytoplasmic EGFP translocation using DAPI
nuclei, then exports cell measurements, well summaries, and dose-response plots.

## Visual walkthrough

[Open the illustrated assay walkthrough on GitHub Pages](https://sebi06.github.io/smartmicroscopy_2026-11/examples/translocation/translocation_docs/translocation-assay.html).
It explains the workflow and includes the plate layout, segmentation,
plate heatmaps, and dose-response plots from an existing saved run. The
[local HTML](translocation_docs/translocation-assay.html) and its plot assets
are stored together in [translocation_docs/](translocation_docs/).
The public page becomes available after these files are pushed and Pages deploys.

Its [code-details section](https://sebi06.github.io/smartmicroscopy_2026-11/examples/translocation/translocation_docs/translocation-assay.html#code)
explains validation, measurements, fitting, and exports. The
[Mermaid source](translocation_docs/translocation-assay-flowchart.mmd) is editable.

## Run the assay

From the workshop root, run:

```powershell
pixi run --locked transloc_assay
```

Inputs are shared workshop assets directly under `data/`:

- `transloc_gfp_dapi_0_2micron.czi`
- `plate_layout_example.xlsx`

Outputs go to `results/translocation/`, not the input-data directory.
The Pixi task explicitly loads the Excel layout; direct Python execution
without `--plate-layout` retains the assay's built-in layout.

The script also accepts CZI, OME-Zarr HCS directories, and OZX archives:

```powershell
pixi run --locked -e default python examples\translocation\translocation_assay.py `
	--input data\transloc_gfp_dapi_0_2micron_ngff_plate.ozx `
	--plate-layout data\plate_layout_example.xlsx `
	--output-dir results/translocation/cli_ozx `
	--plot-backend seaborn
```

Replace `--input` with a CZI file or `.ome.zarr` directory as needed.
`--input-format auto` detects the container; `czi` or `omezarr` require
that format. Use `--input`, not `--czi`. `--reader-backend` selects
`read_stacks` or `read_field` for CZI only; NGFF always uses read-only,
full-resolution field reads without extracting OZX archives.

Use `--help` for all CLI options and separate output folders to preserve runs.
The Python `run_analysis()` API retains its `czi_path` parameter name but
accepts all supported containers with `input_format="auto"`.

## Notebook and outputs

Open [translocation_assay.ipynb](translocation_assay.ipynb) and select the Pixi
**default** kernel
(`.pixi/envs/default/python.exe` on Windows). Its setup cell locates the
workshop root from this example directory or the workshop root and verifies
the environment.

In its configuration cell, select one input:

```python
input_path = data_dir / "transloc_gfp_dapi_0_2micron.czi"
# input_path = data_dir / "transloc_gfp_dapi_0_2micron_ngff_plate.ozx"
# input_path = data_dir / "transloc_gfp_dapi_0_2micron_ngff_plate_zarr3.ome.zarr"
input_format = "auto"  # or "czi" / "omezarr"; mismatches fail early
czi_reader_backend = "read_stacks"  # alternatively "read_field" for CZI
```

Restart the kernel and run all cells after changing configuration. Layout,
channel preview, tuning, segmentation, measurements, fitting, and exports
use the same input adapters and analysis helpers as the CLI. Inputs must
be HCS plates with compatible 2D fields, channels named EGFP then DAPI,
and physical XY scaling.

Notebook outputs go to `results/translocation/notebook_unified_run/<input-name>/`.
Choose a fresh `output_dir` to retain parameter runs. Exports include cell,
well, dose-response and fit CSVs, plots, analysis parameters, and an Excel-layout
snapshot when supplied. Notebook runs also record provenance.

`field_mapping.csv` links field IDs to wells and source paths/selectors.
CZI IDs retain stored scene indices; NGFF IDs follow declared well/image order
and are **not** original CZI indices. Use these IDs with `--segmentation-scene`.

The [calc_dose_response.py](calc_dose_response.py) wrapper runs the same CLI.
Run the included input-adapter tests from the workshop root:

```powershell
pixi run --locked -e default python -m unittest discover -s examples/translocation -p test_translocation_assay_omezarr.py -v
```

Keep the Python modules together for local imports. If the manifest and lockfile
disagree, obtain the matching versions from the instructor rather than bypassing
the check with `--frozen`.

## Primary-Object Thresholding

DAPI nuclei can be segmented with `otsu` (default), `li`, `yen`, `triangle`,
`isodata`, or `mean`, using scikit-image's global threshold algorithms.
Each method computes one threshold per field; cleanup and watershed splitting
are unchanged. EGFP intensities are still measured without display scaling.

Use the notebook's **Threshold** dropdown to compare methods, then set
`threshold_method` in its analysis settings before rerunning analysis and
exports. Preview changes alone do not modify analysis settings or results.
The CLI accepts `--threshold-method yen`, for example; the Python APIs accept
`threshold_method="yen"`. The choice is saved as `DapiThresholdMethod` in
analysis parameters and, for notebook runs, notebook provenance.
