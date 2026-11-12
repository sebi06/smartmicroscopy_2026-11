# Deep Learning Examples

A small PyTorch segmentation workflow, CZANN export, and ONNX Runtime
inference. These are **teaching examples**, not validated production models
or a guide to rigorous model training.

## Setup

From the workshop root, the folder containing [pixi.toml](../../pixi.toml):

```powershell
pixi install --locked
```

Open the notebooks in VS Code, select the workshop's default Pixi kernel,
and execute cells in order. The environment includes PyTorch, torchvision,
czmodel, scikit-image, and ONNX Runtime; no separate notebook `pip install`
is normally needed. GPU access is not required.

The setup uses [workshop_utils.py](../../workshop_utils.py) to locate
`pixi.toml`, add the example directory to imports, and report paths.
For terminal commands use `pixi run --locked ...`: a VS Code interpreter
selection does not activate an existing Conda/base terminal.

## Choose a Notebook

| Notebook | Workflow | Required inputs |
| --- | --- | --- |
| [unpack_czann.ipynb](unpack_czann.ipynb) | Extract a CZANN's metadata and model into a temporary directory. | `data/DL_models/cyto2022_nuc2.czann` |
| [run_prediction_from_czann.ipynb](run_prediction_from_czann.ipynb) | Load a CZANN's ONNX model, predict one image at a time, and compare with labels. | The same CZANN plus nucleus images/labels. |
| [SingleClassSemanticSegmentation_PyTorch.ipynb](SingleClassSemanticSegmentation_PyTorch.ipynb) | Load grayscale PNG pairs, train a simple two-class nuclei model, and export CZANN from an in-memory model or JSON specification. | Nucleus images/labels; JSON specification for the optional disk-conversion section. |

Start with unpacking to inspect an existing model, then inference.
Training/export is independent: **the inference notebook defaults to
`cyto2022_nuc2.czann`, not the model produced by the training notebook**.
Changing models also requires checking input/output layout and preprocessing.

## Inputs and Outputs

- Training and inference read paired files from
  [data/nucleus_data/images/](../../data/nucleus_data/images/) and
  [data/nucleus_data/labels/](../../data/nucleus_data/labels/).
  They are paired by sorted filename order; keep the two lists aligned.
- Shared model inputs live in [data/DL_models/](../../data/DL_models/).
  Optional JSON conversion reads
  `model_conversion_spec_pytorch.json`; its `ModelPath` must identify the
  checkpoint saved by the notebook.
- Training saves `models/saved_torch_segmentation_model.pt` and the direct
  CZANN export relative to the **kernel's working directory**. To use this
  folder's [models/](models/), run with this folder as the working directory.
  JSON conversion writes its CZANN to `data/DL_models`.
- Unpacking uses a temporary directory: extracted files are removed when its
  context exits. The created inference session can still be used afterward.

## Important Caveats

- Training uses 512-pixel crops; inference preprocessing/layout must match
  the chosen model. Do not assume every CZANN has the same channel order,
  patch size, intensity range, or output classes.
- The JSON-export example temporarily allowlists the notebook's own
  `SampleModel` while retaining PyTorch's `weights_only=True` loading.
  Only load trusted checkpoints; do not disable safe loading to accept
  arbitrary files.
- If imports terminate the kernel with an OpenMP conflict, use the matching
  manifest/lockfile, run `pixi install --locked`, and restart the kernel.
  The workshop selects OpenBLAS for NumPy/SciPy. Do not enable
  `KMP_DUPLICATE_LIB_OK`.
- Review save paths before rerunning training/export; checkpoints and
  generated models are outputs, not replacements for the original inputs.
