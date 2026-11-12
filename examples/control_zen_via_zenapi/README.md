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
cd /d "F:\Pixi_Projects\zen_czi\smartmicroscopy_2026-11"
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
  [CMD streaming instructions](../../README.md#stream-a-zen-experiment-to-ome-zarr-from-windows-cmd).
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
