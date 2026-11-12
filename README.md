# Smart Microscopy Workshop

The Pixi workspace is named `pixi_smartmic`. It provides one `default`
environment using Python 3.12 or later and CPU inference on Windows or Linux.
No local repository checkouts or editable installations are needed.

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

### 3. Create Your Workshop Repository

1. Sign in to [GitHub](https://github.com/), creating an account if necessary.
2. Open the workshop template repository using the link from your instructor.
3. Select **Use this template > Create a new repository**.
4. Select your account as the owner and name it `my-smartmic-workshop`.
5. Choose the visibility permitted by your instructor, then select
     **Create repository**.

Your repository is independent of the instructor's template. You can edit
examples and keep your own work without changing the original. Future
changes to the template do not automatically appear in your copy.

If you only want to run the examples, you may instead clone the instructor's
repository directly. A GitHub account is not needed to clone a public
repository, but is needed to create your own copy from the template.

### 4. Clone the Repository

On your new repository's GitHub page, select **Code > HTTPS** and copy the
clone URL. Open PowerShell on Windows or a terminal on Linux, and change to
the directory where you want to keep the workshop, for example:

```text
cd Documents
```

Use the actual HTTPS URL you copied in place of the example below:

```text
git clone https://github.com/YOUR-USERNAME/my-smartmic-workshop.git
cd my-smartmic-workshop
```

If you chose a different repository name, use that name in the `cd` command.
Private repositories require GitHub authentication; follow Git's sign-in
prompts and never put passwords or access tokens in the clone URL.

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

### 5. Create the Workshop Environment

```powershell
pixi install --locked
```

The first installation can take several minutes. Pixi downloads Python and
the required packages into `.pixi/envs/default/`. Let the command finish
successfully before continuing. `--locked` uses the committed lockfile
without updating the workshop's resolved package versions.

Check that Python is available and list the workshop commands:

```powershell
pixi run --locked python --version
pixi task list
```

No `pip install`, developer repository paths, or `refkv` version helper is
needed for this published-package workshop environment.

### 6. Open Napari and a Sample Image

```powershell
pixi run start-napari
```

The napari viewer should open. Close it before starting the sample task
from the same terminal:

```powershell
pixi run open-napari-czitools-example
```

This opens napari with the cell-division sample. The sample may require a
download, so keep your internet connection available.

### 7. Run the Translocation Example

Confirm that the instructor-provided CZI and workbook are present under
`data/translocation/`, then run:

```powershell
pixi run transloc_assay
```

The example reads the shared inputs and writes its outputs under
`results/translocation/`. These generated results and the `.pixi/`
environment are ignored by Git; do not upload them to your repository.
See [Translocation Assay](#translocation-assay) for custom input arguments.

### Returning to the Workshop

Open a terminal in your cloned repository and run `pixi run start-napari`
or another workshop task. You do not need to reinstall Git or Pixi each time.
For an interactive shell, run `pixi shell`. There are no GPU, documentation,
testing, or build environments to select.

### Setup Troubleshooting

- **Command not found:** Reopen your terminal after installing Git or Pixi
    and check `git --version` and `pixi --version` again.
- **Cannot find `pixi.toml`:** Change into the cloned workshop directory.
- **Lockfile out of date:** Ask the instructor for the matching `pixi.toml`
    and `pixi.lock`. Do not run `pixi update` as a workaround during the workshop.
- **Certificate, proxy, or download errors:** Ask your instructor or IT about
    network access and trusted certificates. Do not disable TLS verification.
- **Unsupported platform:** This manifest supports Windows x64 and Linux
    x86-64 only; ask the instructor for a supported workshop computer.
- **Missing dataset:** Obtain the workshop input files from the instructor
    and place them in `data/translocation/` without changing their filenames.
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

The manifest downloads two separate ZEN distributions from release-wheel URLs:

- `zen_api-2026.7.1-py3-none-any.whl` (package version `2026.7.1`)
- `zen_api_utils-0.1.0-py3-none-any.whl` (package version `0.1.0`)

Installing the API alone does not install the utilities. The current manifest
does not require local files in `wheels/`; they are only an alternative if
the instructor deliberately configures an authorized local-wheel handout.
Participants do not need `pixi.toml.template` or the old `paths*.toml`
developer files. There is no setup-script or manifest-regeneration step.

## Folder Layout

```text
smartmic_workshop/
|-- pixi.toml
|-- pixi.lock
|-- wheels/                     Optional authorized local-wheel handout
|-- data/                       Shared input datasets
|   `-- translocation/          Assay CZI and Excel layout
|-- examples/
|   `-- translocation/          Python modules and notebook
`-- results/                    Generated outputs (ignored by Git)
    `-- translocation/
        `-- notebook_run/       Notebook exports
```

Use named subdirectories under `data/` for additional datasets. Examples
can share inputs without duplicating large CZI files. Keep source data
separate from generated tables, plots, and other analysis outputs.

## Tasks

```powershell
pixi task list
pixi run start-napari
pixi run open-napari-czitools-example
pixi run omezarr-gui
pixi run start-zen-streaming
pixi run check-czi-hcs "data/my plate.czi"
pixi run export-hcs "data/my plate.czi"
```

HCS tasks require a supplied CZI path. Export writes a `.hcs.json` file
under `results/hcs/` and overwrites an existing export with the same filename.
An optional second argument selects another output directory. The sample-opening task
uses the installed napari-czitools sample provider, not a repository script.
ZEN streaming requires a compatible running ZEN installation, API access,
and connection settings appropriate to the workshop microscope.

### Translocation Assay

The assay modules and notebook are included under `examples/translocation/`.
The CZI and Excel layout are supplied under `data/translocation/`. Run from
the workshop root:

```powershell
pixi run transloc_assay
```

This reads the shared dataset and workbook, then writes to
`results/translocation/`. The notebook uses
`results/translocation/notebook_run/` so its exports stay separate.

Optional positional arguments are the script, input file, workbook, and output
directory, in that order. For example:

```powershell
pixi run transloc_assay "examples/translocation/translocation_assay.py" "data/translocation/transloc_gfp_dapi_0_2micron.czi" "data/translocation/my_layout.xlsx"
```

Paths passed to tasks are relative to this workshop folder unless absolute.
The assay task explicitly selects the workbook; running the assay script
without `--plate-layout` instead uses its built-in layout. The copied CLI's
default CZI and results directories are resolved from the script location,
not the terminal's working directory.

For interactive use, open the included notebook and select the workshop's
Python interpreter under `.pixi/envs/default/`. Run cells in order. Its
setup discovers the workshop root from the current directory or its parents;
start the notebook from the workshop root or an example subdirectory.

The original development dataset was preserved. Caches, development tests,
editor settings, and previously generated results were not copied into the
example. Confirm dataset distribution permissions before sharing the handout.

## Instructor Notes

The lockfile has been resolved for both supported platforms; this is not a
hardware-streaming or GUI test. No machine-specific certificate path is
configured in the manifest. Configure trusted corporate certificates
locally if your network requires them; do not disable TLS verification.

Development, linting, testing, building, and documentation-deployment tasks
are intentionally excluded from this participant environment.
