"""Launch the CZI -> OME-Zarr converter GUI (czitools Stage 5).

Recommended: run the existing Pixi task from the workshop root::

    pixi run omezarr-gui

Alternatively, run this script in the workshop Pixi environment::

    pixi run python examples/czi_handling/run_omezarr_gui.py

Or run the console script explicitly through Pixi::

    pixi run czitools-omezarr-gui

Selecting a Python interpreter in VS Code does not activate that environment
in an existing terminal. A bare ``czitools-omezarr-gui`` command may therefore
launch the copy installed in Conda base rather than the workshop environment,
causing missing-dependency errors such as ``No module named 'ngff_zarr'``.
Use ``pixi run`` to select the workshop environment and apply its activation.
The workshop manifest already includes ngff-zarr; no separate pip install
is needed.

The GUI can also be embedded in napari::

    from czitools.export_tools import create_gui
    viewer.window.add_dock_widget(create_gui(), name="CZI Converter")
"""

from czitools.export_tools import run_gui

if __name__ == "__main__":
    run_gui()
