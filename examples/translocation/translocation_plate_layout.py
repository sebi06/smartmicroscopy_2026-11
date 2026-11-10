"""Plate annotations, Excel validation, and example workbook generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DOSE_WO = [0.977, 1.95, 3.91, 7.81, 15.63, 31.25, 62.5, 125.0, 250.0]
DOSE_LY = [0.31, 0.63, 1.25, 2.5, 5.0, 10.0, 20.0, 40.0, 80.0]
WELLS_WO = ["A", "B", "C", "D"]
WELLS_LY = ["E", "F", "G", "H"]
DOSE_COLUMNS = ["3", "4", "5", "6", "7", "8", "9", "10", "11"]
DOSE_SERIES = (
    ("Wortmannin", WELLS_WO, DOSE_WO, "nM"),
    ("LY294002", WELLS_LY, DOSE_LY, "uM"),
)
POSITIVE_CONTROL_WELLS = [f"{row}12" for row in WELLS_WO] + [f"{row}1" for row in WELLS_LY]
NEGATIVE_CONTROL_WELLS = [f"{row}1" for row in WELLS_WO] + [f"{row}12" for row in WELLS_LY]
SPECIAL_CONDITIONS = {"A1": "Special condition (39688; unit unspecified)"}


def build_plate_layout(
    *,
    dose_series: tuple[tuple[str, list[str], list[float], str], ...] | None = None,
    dose_columns: list[str] | None = None,
    positive_control_wells: list[str] | None = None,
    negative_control_wells: list[str] | None = None,
    special_conditions: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build well assignments from explicit settings or example defaults.

    Args:
        dose_series: Drug, replicate rows, doses, and dose unit per series.
        dose_columns: Plate columns corresponding to each series' doses.
        positive_control_wells: Positive-control well names.
        negative_control_wells: Negative-control well names.
        special_conditions: Explicit per-well overrides applied last.
    """
    if dose_series is None:
        dose_series = DOSE_SERIES
    if dose_columns is None:
        dose_columns = DOSE_COLUMNS
    if positive_control_wells is None:
        positive_control_wells = POSITIVE_CONTROL_WELLS
    if negative_control_wells is None:
        negative_control_wells = NEGATIVE_CONTROL_WELLS
    if special_conditions is None:
        special_conditions = SPECIAL_CONDITIONS
    layout: dict[str, dict[str, Any]] = {}
    for drug, rows, doses, unit in dose_series:
        for column, dose in zip(dose_columns, doses, strict=True):
            for row in rows:
                well = f"{row}{column}"
                if well in layout:
                    raise ValueError(f"Duplicate treatment assignment for {well}.")
                layout[well] = {"Drug": drug, "Dose": dose, "DoseUnit": unit, "Control": ""}
    for control, wells in (
        ("Positive", positive_control_wells),
        ("Negative", negative_control_wells),
    ):
        for well in wells:
            if well in layout:
                raise ValueError(f"Duplicate control assignment for {well}.")
            layout[well] = {"Drug": "Control", "Dose": np.nan, "DoseUnit": "", "Control": control}
    for well, condition in special_conditions.items():
        layout[well] = {"Drug": "Unassigned", "Dose": np.nan, "DoseUnit": "", "Control": condition}
    return layout


def load_plate_layout(
    path: Path,
    *,
    required_wells: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Read one plate's Excel Wells sheet into analysis-ready assignments.

    Args:
        path: Workbook containing one row per well in the Wells sheet.
        required_wells: Acquired CZI wells that must have annotations, if given.

    Returns:
        Assignments keyed by normalized well name, including extra annotations.

    Raises:
        ValueError: Required annotations are missing, ambiguous, or invalid.
    """
    table = pd.read_excel(path, sheet_name="Wells", engine="openpyxl", dtype=object, keep_default_na=False)
    required_columns = {"PlateID", "Well", "ConditionID", "Role", "Drug", "Dose", "DoseUnit", "Replicate"}
    missing_columns = required_columns - set(table.columns)
    if missing_columns:
        raise ValueError(f"Wells sheet is missing columns: {sorted(missing_columns)}")
    reserved_columns = {
        "Control",
        "WellPath",
        "Row",
        "Column",
        "SceneIndices",
        "FieldCount",
        "NumberOfObjects",
        "MeanIntNuc",
        "MeanIntRing",
        "MeanTranslocationRatio",
        "MedianTranslocationRatio",
        "FractionAboveThreshold",
        "DapiThreshold",
        "RingWidthUm",
        "RingWidthPx",
    }
    if conflicts := reserved_columns.intersection(table.columns):
        raise ValueError(f"Layout columns conflict with analysis results: {sorted(conflicts)}")
    controls = {
        "treatment": "",
        "positive_control": "Positive",
        "negative_control": "Negative",
        "blank": "Blank or unassigned",
        "special": "Special condition",
    }
    layout: dict[str, dict[str, Any]] = {}
    plate_ids: set[str] = set()
    units_by_drug: dict[str, str] = {}
    for excel_row, record in enumerate(table.to_dict(orient="records"), start=2):
        values = {str(key): str(value).strip() for key, value in record.items()}
        if not any(values.values()):
            continue
        match = re.fullmatch(r"([A-Z]+)0*([1-9][0-9]*)", values["Well"].upper())
        if match is None:
            raise ValueError(f"Excel row {excel_row}: invalid well {values['Well']!r}.")
        well = f"{match[1]}{int(match[2])}"
        if well in layout:
            raise ValueError(f"Duplicate well assignment for {well}.")
        if not values["PlateID"] or not values["ConditionID"]:
            raise ValueError(f"Well {well}: PlateID and ConditionID are required.")
        plate_ids.add(values["PlateID"])
        if len(plate_ids) > 1:
            raise ValueError("One CZI run accepts exactly one PlateID; use a separate workbook per plate.")
        role = values["Role"].casefold()
        if role not in controls:
            raise ValueError(f"Well {well}: invalid Role {values['Role']!r}; choose {sorted(controls)}.")
        dose = float("nan")
        if values["Dose"]:
            try:
                dose = float(values["Dose"])
            except ValueError as error:
                raise ValueError(f"Well {well}: Dose must be numeric.") from error
            if not np.isfinite(dose) or dose < 0 or not values["DoseUnit"]:
                raise ValueError(f"Well {well}: Dose must be finite and nonnegative, with a DoseUnit.")
        elif values["DoseUnit"]:
            raise ValueError(f"Well {well}: DoseUnit requires a numeric Dose.")
        if role == "treatment":
            if not values["Drug"] or not np.isfinite(dose) or dose <= 0:
                raise ValueError(f"Well {well}: treatment requires Drug, positive Dose, and DoseUnit.")
            drug = values["Drug"]
            if drug in units_by_drug and units_by_drug[drug] != values["DoseUnit"]:
                raise ValueError(f"Well {well}: use one DoseUnit per drug; convert mixed units before analysis.")
            units_by_drug[drug] = values["DoseUnit"]
        replicate = None
        if values["Replicate"]:
            try:
                replicate_value = float(values["Replicate"])
            except ValueError as error:
                raise ValueError(f"Well {well}: Replicate must be a positive integer or blank.") from error
            if not np.isfinite(replicate_value) or not replicate_value.is_integer() or replicate_value < 1:
                raise ValueError(f"Well {well}: Replicate must be a positive integer or blank.")
            replicate = int(replicate_value)
        control = controls[role]
        if role == "special":
            control = values.get("Notes", "") or values["ConditionID"]
        default_drug = "Control" if role in ("positive_control", "negative_control") else "Unassigned"
        assignment: dict[str, Any] = {str(key): value for key, value in record.items()}
        assignment.update(
            PlateID=values["PlateID"],
            Well=well,
            ConditionID=values["ConditionID"],
            Role=role,
            Drug=values["Drug"] or default_drug,
            Dose=dose,
            DoseUnit=values["DoseUnit"],
            Replicate=replicate,
            Control=control,
        )
        layout[well] = assignment
    if not layout:
        raise ValueError("Wells sheet contains no well assignments.")
    if required_wells is not None and (missing_wells := required_wells - set(layout)):
        raise ValueError(f"Acquired CZI wells are missing from the layout: {sorted(missing_wells)}")
    return layout


def write_example_plate_layout(path: Path) -> None:
    """Create an editable 96-well workbook matching this example assay.

    Args:
        path: Destination workbook; an existing file is never overwritten.
    """
    from openpyxl.styles import Alignment
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.worksheet.table import Table, TableStyleInfo

    if path.exists():
        raise FileExistsError(f"Refusing to overwrite an existing layout: {path}")
    defaults = build_plate_layout()
    records = []
    for row in "ABCDEFGH":
        for column in range(1, 13):
            well = f"{row}{column}"
            assignment = defaults.get(well)
            role, condition, drug, dose, unit, notes = "blank", "blank", "", None, "", ""
            if assignment is not None:
                control = assignment["Control"]
                if control == "":
                    role = "treatment"
                    drug, dose, unit = assignment["Drug"], assignment["Dose"], assignment["DoseUnit"]
                    condition = f"{drug}_{dose:g}_{unit}"
                elif control in ("Positive", "Negative"):
                    role = condition = f"{control.lower()}_control"
                else:
                    role, condition, notes = "special", f"special_{well}", control
            records.append(
                {
                    "PlateID": "Plate01",
                    "Well": well,
                    "ConditionID": condition,
                    "Role": role,
                    "Drug": drug,
                    "Dose": dose,
                    "DoseUnit": unit,
                    "Replicate": (ord(row) - ord("A")) % 4 + 1 if role != "blank" else None,
                    "Notes": notes,
                }
            )
    guide = pd.DataFrame(
        [
            (
                "Wells",
                "One row per well. Edit this sheet; the Python loader reads its column names, not cell positions.",
            ),
            ("PlateID", "One nonempty plate identifier per workbook. One CZI is analyzed per run."),
            (
                "Well",
                "Well name, e.g. A3 or P24. Case and leading column zeros are normalized. Duplicates are rejected.",
            ),
            (
                "ConditionID",
                "Required condition identifier; repeat it across replicate wells. It is an annotation, not a fitting group.",
            ),
            (
                "Role",
                "treatment, positive_control, negative_control, blank, or special. Only treatment wells enter dose-response fits.",
            ),
            (
                "Drug / Dose / DoseUnit",
                "Treatments need a drug and a finite positive dose with a unit. Use one unit per drug. Controls may have optional doses.",
            ),
            (
                "Replicate",
                "Optional positive integer. Example values 1-4 identify rows within each drug block; they do not change pooling.",
            ),
            (
                "Notes",
                "Free text. A1 preserves the original special condition; its dose and unit are unknown and left blank.",
            ),
            (
                "Extra columns",
                "Additional annotations are retained in well summaries. They do not automatically create separate fitting groups.",
            ),
            (
                "Coverage",
                "Every acquired CZI well must appear. Unacquired annotated wells are retained in the layout snapshot.",
            ),
            (
                "Example",
                "96 wells: 72 treatments, 8 positive controls, 7 negative controls, 1 special condition, 8 blank wells in column 2.",
            ),
            ("Fields", "Fields and scenes come from the CZI; do not create duplicate well rows for multiple fields."),
        ],
        columns=["Item", "Description"],
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(records).to_excel(writer, sheet_name="Wells", index=False)
        guide.to_excel(writer, sheet_name="Guide", index=False)
        sheet = writer.sheets["Wells"]
        sheet.freeze_panes = "C2"
        excel_table = Table(displayName="PlateWells", ref=sheet.dimensions)
        excel_table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        sheet.add_table(excel_table)
        roles = DataValidation(type="list", formula1='"treatment,positive_control,negative_control,blank,special"')
        roles.errorTitle = "Invalid well role"
        roles.error = "Choose a role from the dropdown."
        roles.showErrorMessage = True
        sheet.add_data_validation(roles)
        roles.add("D2:D10000")
        for name, width in zip("ABCDEFGHI", (16, 10, 34, 23, 22, 14, 12, 13, 58), strict=True):
            sheet.column_dimensions[name].width = width
        for cell in sheet["F"][1:]:
            cell.number_format = "0.###"
        guide_sheet = writer.sheets["Guide"]
        guide_sheet.freeze_panes = "A2"
        guide_sheet.column_dimensions["A"].width = 25
        guide_sheet.column_dimensions["B"].width = 100
        for cells in guide_sheet.iter_rows(min_row=2):
            guide_sheet.row_dimensions[cells[0].row].height = 42
            cells[1].alignment = Alignment(wrap_text=True, vertical="top")
