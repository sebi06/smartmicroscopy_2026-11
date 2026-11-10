"""Focused input dispatch and read-only NGFF plate adapter checks."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import translocation_assay as assay
import zarr

from translocation_assay_io import load_assay_input, prepare_omezarr_plate, resolve_input_format


class OmeZarrPlateTests(unittest.TestCase):
    """Check metadata validation and independent full-resolution field reads."""

    def setUp(self) -> None:
        """Keep generated stores outside workshop inputs and results."""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def make_plate(
        self,
        *,
        legacy_axes: bool = False,
        unit: str = "micrometer",
        xy_scale: float = 0.2,
        z_size: int = 1,
        second_label: str = "DAPI",
        include_scale: bool = True,
    ) -> Path:
        """Archive two fields in one well plus one declared empty well."""
        directory = self.directory / "plate.zarr"
        root = zarr.open_group(str(directory), mode="w")
        root.attrs["ome"] = {"plate": {"wells": [{"path": "A/01"}, {"path": "B/02"}]}}
        well = root.create_group("A/01")
        well.attrs["ome"] = {"well": {"images": [{"path": "0"}, {"path": "1"}]}}
        empty_well = root.create_group("B/02")
        empty_well.attrs["ome"] = {"well": {"images": []}}
        axes = [{"name": name, **({"unit": unit} if name in ("y", "x") else {})} for name in ("t", "c", "z", "y", "x")]
        for field_index in range(2):
            image = well.create_group(str(field_index))
            transforms = [{"type": "scale", "scale": [1, 1, 1, xy_scale, xy_scale]}] if include_scale else []
            if not legacy_axes:
                transforms = [{"type": "sequence", "transformations": transforms}]
            multiscale = {
                "datasets": [{"path": "scale0", "coordinateTransformations": transforms}],
                **({"axes": axes} if legacy_axes else {"coordinateSystems": [{"name": "intrinsic", "axes": axes}]}),
            }
            image.attrs["ome"] = {
                "multiscales": [multiscale],
                "omero": {
                    "channels": [
                        {"label": "EGFP", "color": "00FF00"},
                        {"label": second_label if field_index else "DAPI", "color": "0000FF"},
                    ]
                },
            }
            image.create_array(
                "scale0",
                data=np.full((1, 2, z_size, 8, 8), field_index + 1, dtype=np.uint16),
            )
        path = self.directory / "plate.ozx"
        with zipfile.ZipFile(path, "w") as archive:
            for member in directory.rglob("*"):
                if member.is_file():
                    archive.write(member, member.relative_to(directory).as_posix())
        return path

    def test_setup_reads_no_pixels(self) -> None:
        """Metadata setup must not invoke array slicing."""
        path = self.make_plate()
        with patch.object(zarr.Array, "__getitem__", side_effect=AssertionError("Pixels read during setup")):
            plate = prepare_omezarr_plate(path)
        self.assertEqual(plate.scene_wells, {0: "A1", 1: "A1"})
        self.assertEqual([well.canonical_name for well in plate.hcs.wells], ["A1", "B2"])
        self.assertEqual(plate.pixel_spacing_um, (0.2, 0.2))

    def test_field_reads_preserve_pixels_and_archive(self) -> None:
        """Read both fields independently without altering the input ZIP."""
        path = self.make_plate()
        original_bytes = path.read_bytes()
        plate = prepare_omezarr_plate(path)
        for index in range(2):
            field = plate.read_field(index)
            self.assertEqual(field.dims, ("T", "C", "Z", "Y", "X"))
            self.assertEqual(field.dtype, np.dtype("uint16"))
            self.assertEqual(field.coords["C"].values.tolist(), ["EGFP", "DAPI"])
            np.testing.assert_array_equal(field.values, index + 1)
        self.assertEqual(path.read_bytes(), original_bytes)
        with self.assertRaises(KeyError):
            plate.read_field(42)

    def test_legacy_axes_and_unit_conversion(self) -> None:
        """Flat NGFF transforms and nanometer axes yield micrometer spacing."""
        plate = prepare_omezarr_plate(self.make_plate(legacy_axes=True, unit="nanometer", xy_scale=200))
        self.assertEqual(plate.pixel_spacing_um, (0.2, 0.2))

    def test_directory_and_archive_share_the_same_interface(self) -> None:
        """Both containers retain field paths and load identical pixels."""
        archive = self.make_plate()
        directory = self.directory / "plate.zarr"
        original_files = {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()}
        inputs = [load_assay_input(path) for path in (directory, archive)]
        self.assertEqual(inputs[0].reader_backend, "omezarr_directory_field")
        self.assertEqual(inputs[1].reader_backend, "omezarr_zip_field")
        for source in inputs:
            self.assertEqual(source.input_format, "omezarr")
            self.assertEqual(source.scene_wells, {0: "A1", 1: "A1"})
            self.assertEqual(source.field_paths, {0: "A/01/0", 1: "A/01/1"})
            arrays, _, count, reader = source.prepare_scene_inputs()
            self.assertIsNone(arrays)
            self.assertEqual(count, 2)
            assert reader is not None
            np.testing.assert_array_equal(reader(1).values, source.preview_reader(1).values)
        self.assertEqual(original_files, {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()})

    def test_detects_czi_case_insensitively(self) -> None:
        """Detection does not read or require CZI pixel contents."""
        path = self.directory / "plate.CZI"
        path.touch()
        self.assertEqual(resolve_input_format(path), "czi")

    def test_rejects_explicit_format_mismatch(self) -> None:
        """A configured format must agree with the selected input container."""
        with self.assertRaisesRegex(ValueError, "Requested czi"):
            load_assay_input(self.make_plate(), input_format="czi")

    def test_rejects_missing_or_unsupported_input(self) -> None:
        """Fail early for missing inputs and non-Zarr directories."""
        with self.assertRaises(FileNotFoundError):
            resolve_input_format(self.directory / "missing.ozx")
        with self.assertRaisesRegex(ValueError, "Choose a CZI"):
            resolve_input_format(self.directory)

    def test_czi_keeps_stored_scene_ids_and_reader_selection(self) -> None:
        """CZI preview uses read_field while analysis keeps its chosen backend."""
        path = self.directory / "plate.czi"
        path.touch()
        metadata = SimpleNamespace(
            scale_required=SimpleNamespace(X=0.2, Y=0.3),
            hcs=SimpleNamespace(
                wells=[
                    SimpleNamespace(
                        canonical_name="A1",
                        canonical_path="A/01",
                        fields=[
                            SimpleNamespace(scene_index=3, field_index=0),
                            SimpleNamespace(scene_index=9, field_index=1),
                        ],
                    )
                ]
            ),
        )
        reader = lambda index: index
        with (
            patch("translocation_assay_io.CziMetadata", return_value=metadata),
            patch("translocation_assay_io.prepare_scene_inputs", return_value=(None, "STCZYX", 2, reader)) as prepare,
        ):
            source = load_assay_input(path, czi_reader_backend="read_stacks")
            self.assertEqual(source.scene_wells, {3: "A1", 9: "A1"})
            self.assertEqual(source.pixel_spacing_um, (0.3, 0.2))
            self.assertEqual(source.field_paths[9], "A/01/field/1")
            prepare.assert_called_once_with(path.resolve(), metadata, "read_field")
            source.prepare_scene_inputs()
            prepare.assert_called_with(path.resolve(), metadata, "read_stacks")

    def test_cli_default_and_legacy_czi_alias(self) -> None:
        """Existing CLI calls keep their input, reader, and ring defaults."""
        path = self.directory / "plate.czi"
        path.touch()
        with (
            patch.object(assay, "_default_czi_path", return_value=path),
            patch.object(assay, "run_analysis") as run,
        ):
            for arguments in ([], ["--input", str(path)], ["--czi", str(path)]):
                with self.subTest(arguments=arguments):
                    run.reset_mock()
                    self.assertEqual(assay.main(arguments), 0)
                    run.assert_called_once()
                    self.assertEqual(run.call_args.kwargs["czi_path"], path)
                    self.assertEqual(run.call_args.kwargs["input_format"], "auto")
                    self.assertEqual(run.call_args.kwargs["reader_backend"], "read_stacks")
                    self.assertEqual(run.call_args.kwargs["ring_width_um"], 2.0)
                    self.assertIsNone(run.call_args.kwargs["ring_width_px"])

    def test_cli_dispatches_ngff_containers_and_pixel_width(self) -> None:
        """Directory inputs are accepted, and pixel widths exclude micrometers."""
        archive = self.make_plate()
        with patch.object(assay, "run_analysis") as run:
            for path in (archive, self.directory / "plate.zarr"):
                with self.subTest(path=path):
                    self.assertEqual(
                        assay.main(
                            [
                                "--input",
                                str(path),
                                "--input-format",
                                "omezarr",
                                "--ring-width-px",
                                "10",
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(run.call_args.kwargs["czi_path"], path)
                    self.assertEqual(run.call_args.kwargs["input_format"], "omezarr")
                    self.assertIsNone(run.call_args.kwargs["ring_width_um"])
                    self.assertEqual(run.call_args.kwargs["ring_width_px"], 10.0)

    def test_cli_rejects_missing_input_and_format_mismatch(self) -> None:
        """Input errors return exit code 2 before invoking analysis."""
        archive = self.make_plate()
        with patch.object(assay, "run_analysis") as run:
            for arguments in (
                ["--input", str(self.directory / "missing.ozx")],
                ["--input", str(archive), "--input-format", "czi"],
                ["--input", str(self.directory)],
            ):
                with self.subTest(arguments=arguments), self.assertLogs(assay.LOGGER, level="ERROR"):
                    self.assertEqual(assay.main(arguments), 2)
            run.assert_not_called()

    def test_cli_analysis_failure_returns_nonzero(self) -> None:
        """Unreadable contents report a runtime failure rather than success."""
        path = self.make_plate()
        with (
            patch.object(assay, "run_analysis", side_effect=ValueError("Invalid plate")),
            self.assertLogs(assay.LOGGER, level="ERROR"),
        ):
            self.assertEqual(assay.main(["--input", str(path)]), 1)

    def test_script_ngff_exports_actual_reader_and_source_mapping(self) -> None:
        """Both NGFF containers bypass CZI checks and use the shared pipeline."""
        archive = self.make_plate()
        results = SimpleNamespace(segmentation_example=None, fields_processed=2, cell_table=pd.DataFrame())
        for path, backend in (
            (archive, "omezarr_zip_field"),
            (self.directory / "plate.zarr", "omezarr_directory_field"),
        ):
            with (
                self.subTest(backend=backend),
                patch.object(assay, "_run_hcs_check") as hcs_check,
                patch.object(assay, "analyze_scenes", return_value=results) as analyze,
                patch.object(assay, "write_analysis_outputs") as write,
            ):
                output_dir = self.directory / backend
                assay.run_analysis(
                    czi_path=path,
                    output_dir=output_dir,
                    ring_width_um=2.0,
                    min_nucleus_area_px=40,
                    min_nucleus_distance_px=8,
                    ratio_threshold=2.0,
                )
                hcs_check.assert_not_called()
                analyze.assert_called_once()
                arguments = analyze.call_args.kwargs
                self.assertIsNone(arguments["scene_arrays"])
                self.assertEqual(arguments["scene_wells"], {0: "A1", 1: "A1"})
                self.assertEqual(arguments["pixel_spacing_um"], (0.2, 0.2))
                np.testing.assert_array_equal(arguments["field_reader"](1).values, 2)
                parameters = write.call_args.args[2]
                self.assertEqual(parameters["InputFormat"], "omezarr")
                self.assertEqual(parameters["ReaderBackend"], backend)
                self.assertEqual(parameters["InputOmeZarr"], str(path.resolve()))
                self.assertEqual(parameters["NgffResolutionLevel"], 0)
                self.assertNotIn("InputCzi", parameters)
                self.assertIn("not original CZI scene IDs", parameters["FieldIndexMeaning"])
                mapping = pd.read_csv(output_dir / parameters["FieldMappingFile"])
                self.assertEqual(mapping.SceneIndex.tolist(), [0, 1])
                self.assertEqual(mapping.FieldPath.tolist(), ["A/01/0", "A/01/1"])

    def test_rejects_non_singleton_z(self) -> None:
        """Do not silently project 3D images for this 2D assay."""
        with self.assertRaisesRegex(ValueError, "2D channel planes"):
            prepare_omezarr_plate(self.make_plate(z_size=2))

    def test_rejects_missing_scale(self) -> None:
        """Never infer physical spacing from absent transforms."""
        with self.assertRaisesRegex(ValueError, "Missing NGFF physical scale"):
            prepare_omezarr_plate(self.make_plate(include_scale=False))

    def test_rejects_inconsistent_channels(self) -> None:
        """Every field must agree on channel identities."""
        with self.assertRaisesRegex(ValueError, "Inconsistent channels"):
            prepare_omezarr_plate(self.make_plate(second_label="Other"))

    def test_rejects_unsupported_units(self) -> None:
        """Pixel units cannot be treated as physical micrometers."""
        with self.assertRaisesRegex(ValueError, "Unsupported spatial unit"):
            prepare_omezarr_plate(self.make_plate(unit="pixel"))


if __name__ == "__main__":
    unittest.main()
