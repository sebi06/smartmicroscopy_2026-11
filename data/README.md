# Workshop Data

Inputs are shared across examples, not duplicated beside individual scripts.
The current CZI files and translocation workbook live directly in this folder.
Models are under `DL_models/`; paired training images and labels are under
`nucleus_data/`. Add future datasets in named subdirectories and document their
source, filenames, and distribution restrictions.

Treat supplied inputs as read-only. Generated tables, plots, and exports
belong under the workshop's `results/` directory. CZI files at any depth
are managed by Git LFS, including uppercase or mixed-case extensions.
Install Git LFS before adding CZI datasets. Normal `git add` and `git commit`
then use the root `.gitattributes`; existing history is not migrated.

After cloning, run `git lfs install --local` and `git lfs pull` from the
repository root to download the datasets. GitHub LFS storage and bandwidth
quotas apply. Datasets can instead be distributed separately while preserving
this directory layout.

## Translocation Dataset

- [transloc_gfp_dapi_0_2micron.czi](transloc_gfp_dapi_0_2micron.czi):
  CZI assay input.
- [transloc_gfp_dapi_0_2micron_ngff_plate.ozx](transloc_gfp_dapi_0_2micron_ngff_plate.ozx):
  OME-Zarr HCS archive alternative.
- [plate_layout_example.xlsx](plate_layout_example.xlsx): Well annotations and
  dose assignments. This workbook is tracked even though new `.xlsx` files are
  ignored by default; intentionally add replacement handouts with `git add -f`.

These inputs were copied from the local Translocation_exp dataset.
Confirm permission to distribute the dataset before handing it out outside
the authorized workshop audience. Analysis outputs belong in
`results/translocation/` at the workshop root.
