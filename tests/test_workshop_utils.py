"""Tests for notebook root discovery and kernel validation."""

import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from workshop_utils import initialize_workshop


class WorkshopSetupTests(unittest.TestCase):
    def setUp(self):
        path_patch = patch.object(sys, "path", sys.path.copy())
        path_patch.start()
        self.addCleanup(path_patch.stop)
        self.output = StringIO()
        output_redirect = redirect_stdout(self.output)
        output_redirect.__enter__()
        self.addCleanup(output_redirect.__exit__, None, None, None)

    def test_root_and_nested_directory_need_only_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "pixi.toml").touch()
            nested = root / "examples" / "new_topic"
            nested.mkdir(parents=True)
            with patch.object(sys, "prefix", str(root / ".pixi" / "envs" / "default")):
                self.assertEqual(initialize_workshop("new_topic", start=root)[0], root)
                self.assertEqual(initialize_workshop("new_topic", start=nested)[0], root)
                with patch("workshop_utils.Path.cwd", return_value=nested):
                    self.assertEqual(initialize_workshop("new_topic")[0], root)

    def test_nearest_manifest_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "pixi.toml").touch()
            child = root / "nested_workshop"
            child.mkdir()
            (child / "pixi.toml").touch()
            with patch.object(sys, "prefix", str(child / ".pixi" / "envs" / "default")):
                self.assertEqual(initialize_workshop("new_topic", start=child)[0], child)

    def test_missing_manifest_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, "pixi.toml"):
                initialize_workshop("new_topic", start=Path(directory))

    def test_wrong_kernel_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pixi.toml").touch()
            with patch.object(sys, "prefix", str(root / "other_environment")):
                with self.assertRaisesRegex(RuntimeError, "Select the workshop Pixi default kernel"):
                    initialize_workshop("new_topic", start=root)

    def test_paths_imports_and_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "pixi.toml").touch()
            with patch.object(sys, "prefix", str(root / ".pixi" / "envs" / "default")):
                paths = initialize_workshop("czi_handling", start=root)
                self.assertEqual(paths, (
                    root,
                    root / "examples" / "czi_handling",
                    root / "data",
                    root / "data" / "DL_models",
                ))
                self.assertEqual(sys.path[0], str(paths[1]))
                self.assertEqual(self.output.getvalue().splitlines(), [
                    f"Kernel Python: {sys.executable}",
                    f"Workshop: {paths[0]}",
                    f"Project: {paths[1]}",
                    f"Data: {paths[2]}",
                    f"Model: {paths[3]}",
                ])
                initialize_workshop("czi_handling", start=root)
                self.assertEqual(sys.path.count(str(paths[1])), 1)

    def test_data_subdirectory_keeps_shared_model_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "pixi.toml").touch()
            with patch.object(sys, "prefix", str(root / ".pixi" / "envs" / "default")):
                _, _, data_dir, model_dir = initialize_workshop(
                    "translocation", start=root, data_subdir="translocation"
                )
                self.assertEqual(data_dir, root / "data" / "translocation")
                self.assertEqual(model_dir, root / "data" / "DL_models")
