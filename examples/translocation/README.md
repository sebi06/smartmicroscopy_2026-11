# Translocation Assay

This example measures nuclear-to-cytoplasmic EGFP translocation using DAPI
nuclei, then exports cell measurements, well summaries, and dose-response plots.

From the workshop root, run:

```powershell
pixi run transloc_assay
```

Inputs are shared workshop assets under `data/translocation/`:

- `transloc_gfp_dapi_0_2micron.czi`
- `plate_layout_example.xlsx`

Outputs go to `results/translocation/`, not the input-data directory.
The Pixi task explicitly loads the Excel layout; direct Python execution
without `--plate-layout` retains the assay's built-in layout.

The script also accepts CZI, OME-Zarr HCS directories, and OZX archives:

```powershell
pixi run -e default python examples/translocation/translocation_assay.py `
	--input data/translocation/transloc_gfp_dapi_0_2micron_ngff_plate.ozx `
	--plate-layout data/translocation/plate_layout_example.xlsx `
	--output-dir results/translocation/cli_ozx `
	--plot-backend seaborn
```

Replace `--input` with a CZI file or `.ome.zarr` directory as needed.
`--input-format auto` is the default; `czi` or `omezarr` explicitly require
that format. The existing `--czi` argument remains an alias for `--input`,
so the Pixi task and older commands still work. `--reader-backend` selects
`read_stacks` or `read_field` for CZI only; NGFF always uses read-only,
full-resolution field reads without extracting OZX archives.

Script exports now include `field_mapping.csv` and format-aware analysis
parameters. NGFF field IDs follow declared well/image order, not original
CZI scene IDs. Select previews with `--segmentation-scene` using those
mapped IDs. Use separate output folders to retain runs from different
inputs or settings. The Python `run_analysis()` API retains its historical
`czi_path` parameter name for compatibility, but accepts any supported
container and an optional `input_format="auto"` argument.

Open **`translocation_assay.ipynb`** for the unified CZI, OME-Zarr directory,
and OZX workflow. Select the local Pixi **default** kernel
(`.pixi/envs/default/python.exe` on Windows). Its setup cell locates the
workshop root from this example directory or the workshop root and verifies
the environment. The earlier OME-Zarr-only notebook is no longer the
recommended workflow.

In the original notebook's configuration cell, select one input:

```python
input_path = data_dir / "transloc_gfp_dapi_0_2micron.czi"
# input_path = data_dir / "transloc_gfp_dapi_0_2micron_ngff_plate.ozx"
# input_path = data_dir / "transloc_gfp_dapi_0_2micron_ngff_plate_zarr3.ome.zarr"
input_format = "auto"  # or "czi" / "omezarr"; mismatches fail early
czi_reader_backend = "read_stacks"  # alternatively "read_field" for CZI
```

Restart the kernel and run all cells after changing configuration. Layout,
channel preview, tuning, segmentation, measurements, fitting, and exports
are shared. NGFF sources are read-only and use one full-resolution field
at a time; OZX requires neither extraction nor the original CZI. Only HCS
plates with compatible 2D fields, named channels, and physical XY scaling
are supported. The script uses the same input adapters and analysis helpers.

Outputs go to `results/translocation/notebook_run/<input-name>/`.
Choose a fresh `output_dir` to retain different parameter runs of one input.
`field_mapping.csv` links analysis field indices to wells and source image
paths/selectors. CZI indices retain stored scene IDs; NGFF indices follow
declared well/image order and are **not** original CZI scene IDs. Parameters
and provenance record the actual input format, backend, and field-ID meaning.

Run the focused input-adapter tests from the workshop root:

```powershell
pixi run -e default python -m unittest discover -s examples/translocation -p test_translocation_assay_omezarr.py -v
```

If the current manifest cannot resolve, `pixi run --frozen -e default ...`
uses the existing lockfile/environment without updating dependencies.

The Python modules stay together for local imports. `calc_dose_response.py`
is a compatibility entry point for the same assay CLI. Original development
tests and previously generated outputs are not included in this example.

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
