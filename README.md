# Smart Microscopy Workshop

## Presentation and Visual Overview

- [Smart Microscopy in ZEN — visual overview](https://sebi06.github.io/smartmicroscopy/presentation/smart-microscopy-zen.html):
  explore the interfaces, workflows, examples, and videos.
- [Smart Microscopy in ZEN — presentation slides](https://sebi06.github.io/smartmicroscopy/presentation/smart-microscopy-zen-slides.html):
  open the slide deck; use the arrow keys to navigate and **O** for the outline.

Offline copies are included in [presentation/](presentation/). Keep the
`assets/` folder beside the HTML files so images and videos remain available.

## Workshop Environment

The Pixi workspace is named `pixi_smartmic`. It provides one `default`
environment using Python 3.12 and CPU inference on Windows or Linux.
No local repository checkouts or editable installations are needed.

## Quick Start

With Git, Git LFS, and Pixi installed, run:

```text
git clone https://github.com/sebi06/smartmicroscopy.git
cd smartmicroscopy
git lfs install --local
git lfs pull
pixi install --locked
pixi run --locked check-install
pixi run --locked start-napari
```

`check-install` checks imports and CPU-only PyTorch without opening a GUI
or connecting to a microscope. For first-time installation, follow the
steps below. For individual examples, see
[CZI handling](examples/czi_handling/README.md),
[deep learning](examples/deep_learning/README.md),
[translocation](examples/translocation/README.md), and
[ZEN control](examples/control_zen_via_zenapi/README.md).

## Participant Setup

Complete these steps before the workshop. You need a Windows x64 or Linux
x86-64 computer with a graphical desktop, an internet connection, and space
for the environment and datasets. macOS and ARM platforms are not configured
in this workshop manifest. No GPU is required.

Pixi installs Python and the workshop packages for you. You do not need to
install Python, Anaconda, or individual Python packages separately.

### 1. Install Git

Git downloads the workshop repository to your computer.

**Windows:** Open PowerShell from the Start menu and run:

```powershell
winget install --id Git.Git --exact --source winget
```

Follow any installer prompts. If `winget` is unavailable, download and run
the [Git for Windows installer](https://git-scm.com/install/windows), using
the default options and allowing Git on the command-line PATH.
On a managed computer, ask IT to install it if necessary.

**Linux:** On Ubuntu or Debian, open a terminal and run:

```bash
sudo apt update
sudo apt install git git-lfs curl
```

For other distributions, use the appropriate package manager described in
the [Git Linux installation guide](https://git-scm.com/install/linux).

Close and reopen your terminal, then check:

```text
git --version
```

You should see a Git version number rather than a command-not-found error.

Check Git LFS as well; CZI datasets are stored using Git Large File Storage:

```text
git lfs version
```

Git for Windows normally includes Git LFS. If the command is unavailable,
install it using the [Git LFS installation guide](https://git-lfs.com/).

### 2. Install Pixi

Pixi creates an isolated environment with the workshop's package versions.

**Windows:** In PowerShell, run:

```powershell
winget install --id prefix-dev.pixi --exact --source winget
```

If `winget` is unavailable, use the Windows MSI installer linked from the
[official Pixi installation guide](https://pixi.prefix.dev/latest/installation/).
Follow the installer prompts and consult IT if installation is restricted.

**Linux:** Run the official installer in your terminal:

```bash
curl -fsSL https://pixi.sh/install.sh | sh
```

This command downloads and executes the official installation script. You
can inspect the script at that URL before running it.

Close and reopen your terminal, then check:

```text
pixi --version
```

You should see a Pixi version number. If either Git or Pixi is still not
recognized, restart your terminal application or computer and check the
installation guide. Do not continue until both commands work.

### 3. Clone the Repository

Open a terminal in the directory where you want to keep the workshop:

```text
git clone https://github.com/sebi06/smartmicroscopy.git
cd smartmicroscopy
```

No GitHub account is needed to clone this public repository.
If the instructor requests your own copy, sign in to GitHub and select
**Use this template > Create a new repository**, choose the permitted visibility,
then clone your copy's HTTPS URL instead. Template copies are independent;
future instructor changes do not arrive automatically. Private copies require
authentication; never put credentials in the clone URL.

Your current directory should now contain `pixi.toml`, `pixi.lock`,
`examples/`, and `data/`. Run the remaining commands from this directory.

Initialize Git LFS for this clone and download its datasets:

```text
git lfs install --local
git lfs pull
```

These downloads require additional disk space and network access. GitHub
LFS storage, bandwidth, and per-file limits depend on the repository owner's
plan. If datasets are distributed separately, obtain them from the instructor.

### 4. Create the Workshop Environment

```powershell
pixi install --locked
```

The first installation can take several minutes. Pixi downloads Python and
the required packages into `.pixi/envs/default/`. Let the command finish
successfully before continuing. `--locked` uses the committed lockfile
without updating the workshop's resolved package versions.

Check that Python is available and list the workshop commands:

```powershell
pixi run --locked check-install
pixi task list
```

No `pip install`, developer repository paths, or `refkv` version helper is
needed for this published-package workshop environment.

### 5. Open Napari and a Sample Image

```powershell
pixi run --locked start-napari
```

The napari viewer should open. Close it before starting the sample task
from the same terminal:

```powershell
pixi run --locked open-napari-czitools-example
```

This opens napari with the cell-division sample. The sample may require a
download, so keep your internet connection available.

### 6. Run the Translocation Example

Confirm that the instructor-provided CZI and workbook are present under
`data/`, then run:

```powershell
pixi run --locked transloc_assay
```

The example reads the shared inputs and writes its outputs under
`results/translocation/`. These generated results and the `.pixi/`
environment are ignored by Git; do not upload them to your repository.
See [Translocation Assay](#translocation-assay) for custom input arguments.

### Returning to the Workshop

Open a terminal in your cloned repository and run `pixi run start-napari`
or another workshop task. You do not need to reinstall Git or Pixi each time.
For an interactive shell, run `pixi shell`. There is only one environment,
`default`; `pixi run --locked` selects it automatically.

### Shared Notebook Setup

The notebook setup cells load `initialize_workshop()` from
[workshop_utils.py](workshop_utils.py). It walks from the current working
directory through its parents and uses only the nearest `pixi.toml` to find
the workshop root. No particular notebook or example file is required for
root discovery. The utility respects the interpreter selected in VS Code
or used to launch a script; it does not require the environment to live
inside this workshop. That environment must provide the required packages.

Run notebooks from the workshop root or any subdirectory. A small import
bootstrap locates the shared utility without installing a local package.
The utility adds the example directory to `sys.path` and reports the interpreter
and paths. Notebooks select their example folder:

```python
workshop_root, project_dir, data_dir, model_dir = initialize_workshop("czi_handling")
```

The returned paths point to the workshop root, `examples/<example>`, `data`,
and `data/DL_models`. Workshop inputs, including the translocation CZI and
Excel layout, currently live directly in `data/`. The optional `data_subdir`
argument supports datasets in a subfolder; it does not move existing files.

### Setup Troubleshooting

- **Command not found:** Reopen your terminal after installing Git or Pixi
    and check `git --version` and `pixi --version` again.
- **Cannot find `pixi.toml`:** Change into the cloned workshop directory.
- **Environment directory has moved:** Pixi environments are not relocatable.
    Close kernels and applications using this workshop environment, remove only
    `.pixi/envs/default/` from the renamed repository, then run
    `pixi install --locked` and `pixi run --locked check-install`.
    Keep `pixi.lock`; do not edit environment path markers to bypass this check.
- **Lockfile out of date:** Ask the instructor for the matching `pixi.toml`
    and `pixi.lock`. Do not run `pixi update` as a workaround during the workshop.
- **Certificate, proxy, or download errors:** Ask your instructor or IT about
    network access and trusted certificates. Do not disable TLS verification.
- **Unsupported platform:** This manifest supports Windows x64 and Linux
    x86-64 only; ask the instructor for a supported workshop computer.
- **Missing dataset:** Obtain the workshop input files from the instructor
    and place them in `data/` without changing their filenames. A small CZI
    containing text beginning with `version https://git-lfs` is an LFS pointer;
    rerun `git lfs pull` rather than opening it as an image.
- **Missing extras warnings:** Some upstream PyPI packages request extras
    unavailable on conda packages. These warnings can occur during resolution;
    an installation error or failed `check-install` still needs investigation.
- **OpenMP kernel crash when combining PyTorch and scikit-image:** The manifest
    selects OpenBLAS rather than MKL for NumPy/SciPy to avoid competing OpenMP
    runtimes. Run `pixi install --locked` with the matching manifest and lockfile,
    then restart the notebook kernel. Do not set `KMP_DUPLICATE_LIB_OK`; it can
    hide unsafe runtime conflicts.

If installation fails, share the error text with the instructor, but remove
any credentials or private network details before posting it publicly.

## Package Sources

Internet access is required for the initial installation. Workshop packages,
including `napari-zenapi-streaming`, are installed from published releases,
not editable developer checkouts. `pixi.lock` records the resolved versions.
PyTorch and torchvision use the official CPU-only wheel index, avoiding CUDA
downloads on Linux as well as Windows. Python is kept on the tested 3.12 line.

The manifest downloads two separate ZEN distributions from release-wheel URLs:

- `zen_api-2026.7.1-py3-none-any.whl` (package version `2026.7.1`)
- `zen_api_utils-0.1.0-py3-none-any.whl` (package version `0.1.0`)

Installing the API alone does not install the utilities. No local `wheels/`
folder, developer checkout, or manifest-generation step is required.

## Folder Layout

```text
smartmicroscopy/
|-- pixi.toml
|-- pixi.lock
|-- data/                       Shared input datasets
|   |-- transloc_gfp_dapi_0_2micron.czi
|   |-- plate_layout_example.xlsx
|   |-- DL_models/
|   `-- nucleus_data/
|-- examples/
|   |-- czi_handling/
|   |-- deep_learning/
|   |-- control_zen_via_zenapi/
|   `-- translocation/
`-- results/                    Generated outputs (ignored by Git)
    `-- translocation/
        `-- notebook_unified_run/
```

Use named subdirectories under `data/` for additional datasets. Examples
can share inputs without duplicating large CZI files. Keep source data
separate from generated tables, plots, and other analysis outputs.

## Tasks

```powershell
pixi task list
pixi run --locked check-install
pixi run --locked start-napari
pixi run --locked open-napari-czitools-example
pixi run --locked omezarr-gui
pixi run --locked start-zen-streaming
pixi run --locked check-czi-hcs "data/my plate.czi"
pixi run --locked export-hcs "data/my plate.czi"
```

HCS tasks require a supplied CZI path. Export writes a `.hcs.json` file
under `results/hcs/` and overwrites an existing export with the same filename.
An optional second argument selects another output directory. The sample-opening task
uses the installed napari-czitools sample provider, not a repository script.
ZEN streaming requires a compatible running ZEN installation, API access,
and connection settings appropriate to the workshop microscope.

### Stream a ZEN Experiment to OME-Zarr from Windows CMD

Use [zenapi_stream2omezarr_experiment.py](examples/control_zen_via_zenapi/zenapi_stream2omezarr_experiment.py)
to stream an experiment directly to OME-Zarr, rather than opening the napari
streaming viewer.

Open **Command Prompt (CMD)** in your checkout:

```bat
cd /d "F:\Pixi_Projects\zen_czi\smartmicroscopy"
pixi run --locked -e default python "examples\control_zen_via_zenapi\zenapi_stream2omezarr_experiment.py" --help
```

The workspace name is `pixi_smartmic` and the environment name is `default`
(shown together as `pixi_smartmic:default` in VS Code). Pass only `default`
to `-e`. Pixi selects the workspace from the current directory and runs its
Python interpreter; no Conda activation or VS Code interpreter selection is
required. Do not use the interpreter from the separate `zen-pixi-workspace`.
For gateway setup, the full acquisition command, manual startup, and overwrite
precautions, see the [CMD example](examples/control_zen_via_zenapi/README.md#cmd-streaming-example).

### Translocation Assay

The assay modules and notebook are included under `examples/translocation/`.
The CZI and Excel layout are supplied under `data/`. Run from
the workshop root:

```powershell
pixi run --locked transloc_assay
```

This reads the shared dataset and workbook, then writes to
`results/translocation/`. The notebook uses
`results/translocation/notebook_unified_run/<input-name>/` so its exports stay separate.

Optional positional arguments are the script, input file, workbook, and output
directory, in that order. For example:

```powershell
pixi run --locked transloc_assay "examples/translocation/translocation_assay.py" "data/transloc_gfp_dapi_0_2micron.czi" "data/my_layout.xlsx"
```

Paths passed to tasks are relative to this workshop folder unless absolute.
The assay task explicitly selects the workbook; running the assay script
without `--plate-layout` instead uses its built-in layout. The copied CLI's
default CZI and results directories are resolved from the script location,
not the terminal's working directory.

See the [assay README](examples/translocation/README.md) for notebook setup,
input formats, parameters, and plots. Confirm dataset distribution permissions
before sharing the handout.

## Instructor Notes

Commit `pixi.toml` and `pixi.lock` together after changes, run `pixi lock --check`,
and test `pixi install --locked` on a clean participant machine before handout.
Resolving both platforms is not a Linux runtime, hardware-streaming, or GUI test.
No machine-specific certificate path is
configured in the manifest. Configure trusted corporate certificates
locally if your network requires them; do not disable TLS verification.

Development, linting, testing, building, and documentation-deployment tasks
are intentionally excluded from this participant environment.

## DISCLAIMER

The provided examples are free to use for everybody. Carl Zeiss Microscopy GmbH's ZEN software undertakes no warranty concerning the use of those scripts, image analysis settings and ZEN experiments.

> :warning: **Use scripts, tools, ZEN API and all examples at your own risk!**

Additionally Carl Zeiss Microscopy GmbH's ZEN software allows connection and usage to the third party software packages.
Therefore Carl Zeiss Microscopy GmbH undertakes no warranty concerning those software packages, makes no representation that they will work on your system and/or hardware and will not be liable for any damages caused by the use of any scripts or examples inside this repository.

By using any of those examples you agree to this disclaimer.

Version: 2026.11.12

Copyright (c) 2026 Carl Zeiss AG, Germany. All Rights Reserved.
