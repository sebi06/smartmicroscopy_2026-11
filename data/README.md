# Workshop Data

Keep input datasets in this shared directory, grouped by dataset or topic,
rather than storing separate copies alongside individual examples.

`translocation/` contains the CZI assay dataset and its Excel plate layout.
Examples may reuse these files. Add future datasets in their own named
subdirectories and document their source, expected filenames, and any
distribution restrictions here.

Treat supplied inputs as read-only. Generated tables, plots, and exports
belong under the workshop's `results/` directory. CZI files at any depth
are managed by Git LFS, including uppercase or mixed-case extensions.
Install Git LFS before adding datasets; use normal `git add` and `git commit`
commands afterward. Commit the root `.gitattributes` together with the first
LFS-managed files. Existing Git history is not migrated automatically.

After cloning, run `git lfs install --local` and `git lfs pull` from the
repository root to download the datasets. GitHub LFS storage and bandwidth
quotas apply. Datasets can instead be distributed separately while preserving
this directory layout.

## Translocation Dataset

- `transloc_gfp_dapi_0_2micron.czi`: CZI input for the translocation assay.
- `plate_layout_example.xlsx`: Example well annotations and dose assignments.

These inputs were copied from the local Translocation_exp dataset.
Confirm permission to distribute the dataset before handing it out outside
the authorized workshop audience. Analysis outputs belong in
`results/translocation/` at the workshop root.
