# Control ZEN through ZEN-API

Examples for microscope control, experiment configuration, image streaming,
and guided acquisition.

**These scripts can move hardware, acquire images, and change or overwrite
experiment/output files. Review their settings before running on a microscope.**

## Setup and launch

- Install the workshop's `pixi_smartmic:default` environment; see the
  [workshop setup](../../README.md).
- Start a compatible ZEN installation with ZEN-API enabled.
- Configure the gateway INI beside the selected script. Examples use either
  `config.ini` or `my_config.ini`; check the script's selected path.
- Adapt experiment names, stage coordinates, input files, and output paths
  to your microscope. Examples that open images in ZEN also need TCP/IP access.

From **Windows CMD**, launch a selected script using the workshop environment:

```bat
cd /d "F:\Pixi_Projects\zen_czi\smartmicroscopy"
pixi run --locked -e default python "examples\control_zen_via_zenapi\zenapi_streaming.py"
```

Replace the script name with the example you need. Most examples are configured
inside their source rather than through command-line flags.

## Hardware and experiment examples

- **Changers:** [zenapi_changers.py](zenapi_changers.py) queries and changes
  optical components; [zenapi_objectivechanger.py](zenapi_objectivechanger.py)
  demonstrates objective and optovar positions.
- **Stage and focus:** [zenapi_stage_LM.py](zenapi_stage_LM.py) moves the XY stage;
  [zenapi_zdrive.py](zenapi_zdrive.py) controls focus/surface finding;
  [zenapi_stage_LM_stagemarks.py](zenapi_stage_LM_stagemarks.py) visits positions
  from a stage-mark file.
- **Acquisition settings:** [zenapi_positions.py](zenapi_positions.py) adds
  acquisition positions; [zenapi_tileregion.py](zenapi_tileregion.py) modifies
  tile regions; [zenapi_zstack.py](zenapi_zstack.py) modifies and runs Z-stacks.
- **Autofocus and monitoring:** [zenapi_swaf.py](zenapi_swaf.py) configures and
  runs software autofocus; [zenapi_experiment_status.py](zenapi_experiment_status.py)
  starts an experiment and monitors its status.

## Streaming

- [zenapi_streaming.py](zenapi_streaming.py): live PyQtGraph display with
  optional thresholding, semantic segmentation, or denoising.
- [zenapi_stream2omezarr_experiment.py](zenapi_stream2omezarr_experiment.py):
  experiment-metadata-driven OME-Zarr streaming, with a CLI and Python API.
  Run it with `--help` for arguments; see the
  [CMD example below](#cmd-streaming-example).
- [zenapi_stream_omezarr_simple.py](zenapi_stream_omezarr_simple.py):
  configured Python example with optional pyramids and output validation.

## Guided acquisition

[zenapi_guidedacq.py](zenapi_guidedacq.py) segments a saved overview and runs
live detail scans for the detected regions. Optional settings collect run
files and show a final comparison plot.

See the **[guided-acquisition README](guided_acquisition_docs/README_guided_acquisition.md)**
for setup, options, output locations, and the linked visual walkthrough,
flowchart, and sequence diagram.

## Supporting files

- [processing_tools.py](processing_tools.py): image processing, segmentation,
  object measurements, and stage-coordinate conversion.
- [onnx_inference.py](onnx_inference.py): ONNX model inference helpers.
- [StageMarks_Brainslide_CD7.czstm](StageMarks_Brainslide_CD7.czstm): example
  stage marks; verify coordinates against your sample before use.

Keep gateway credentials private. Output locations vary by example; check
the script and ZEN's configured image output directory before acquisition.

## CMD streaming example

Start a compatible ZEN installation with ZEN-API enabled and make the named
experiment available. Configure [config.ini](config.ini) for your gateway
(or create the local `my_config.ini` if selected by your script).
The gateway INI is required; streaming dimensions come from ZEN's exported
experiment metadata, not a separate streaming INI.

From the workshop root in **CMD**, start acquisition and write OME-Zarr:

```bat
pixi run --locked -e default python "examples\control_zen_via_zenapi\zenapi_stream2omezarr_experiment.py" ^
  --experiment "00_ZEN_API_OMEZARR_Stream" ^
  --zenapi-config "examples\control_zen_via_zenapi\config.ini" ^
  --output-dir "results\zen-streaming" ^
  --dtype uint16 ^
  --czi-name "zenapi_stream" ^
  --start-experiment ^
  --no-overwrite-czi ^
  --no-overwrite-zarr
```

- CMD's `^` continues a line; do not put spaces after it. Alternatively, join
  the lines with spaces and remove the carets.
- Replace the experiment name (without `.czexp`) and match `--dtype` to its pixels.
  Quote paths with spaces. `--output-dir` affects OME-Zarr, not ZEN's CZI location.
- For manual startup, use `--no-start-experiment` (the default), launch the script,
  then start the experiment in ZEN. Increase the default 30-second inactivity
  timeout with `--inactivity-timeout 120` if needed.
- Both `--no-overwrite-*` flags protect existing outputs; overwriting is otherwise
  enabled by default.
- Optional: `--validate-ome-zarr` validates metadata; `--pyramid-levels 3` adds
  three downsampled levels afterward. Explicit sample-carrier wells select an
  HCS plate layout by default.
