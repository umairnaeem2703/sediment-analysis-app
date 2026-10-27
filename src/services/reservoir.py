"""The reservoir curve of one dam (FR-M4-01, FR-M4-02, B3.3).

`curve_inputs` gives the inputs of step 6: the dam sheet's values, with the edits the user kept on the dam, Hmin and the
shape class. `validate_curve_entries` and `apply_curve_settings` turn the entered texts into numbers and keep them on
the dam; `parse_table_step` reads the level interval of the table. `compute_curve` and `compute_dam_curve` fit the curve
and make its table and warnings. `write_reservoir_csv` writes `reservoir_curve.csv` into a folder it is given; the run
folder itself belongs to the reporting service (M5).
"""

import math
from pathlib import Path
from typing import List, NamedTuple, Optional

import pandas as pd

from src.core.reservoir import (
    STEP_M,
    ReservoirCurve,
    check_inputs,
    check_shape,
    check_step,
    curve_table,
    curve_warnings,
    fit_curve,
)
from src.services.project import CurveOverrides, Dam, Project
from src.services.regional import DamSheet, cell_text, parse_number, quote_cell

CSV_NAME = "reservoir_curve.csv"

# input -> (words, symbol, unit), in the order of FR-M4-01
FIELDS = {
    "bed_elev_m": ("Bed elevation", "Hbed", "m"),
    "h_min_m": ("Minimum operating level", "Hmin", "m"),
    "max_elev_m": ("Maximum level", "Hmax", "m"),
    "crest_elev_m": ("Crest elevation", "Hcrest", "m"),
    "active_vol_hm3": ("Active volume", "Vactive", "hm³"),
    "max_vol_hm3": ("Maximum volume", "Vmax", "hm³"),
}
_SHEET_FIELDS = [name for name in FIELDS if name != "h_min_m"]  # the inputs the dam sheet holds


class CurveInputs(NamedTuple):
    bed_elev_m: float
    h_min_m: Optional[float]
    max_elev_m: float
    crest_elev_m: float
    active_vol_hm3: float
    max_vol_hm3: float
    shape_class: Optional[str]


class CurveResult(NamedTuple):
    curve: ReservoirCurve
    table: pd.DataFrame  # Elevation_m, Volume_hm3, Area_km2
    h_min_given: bool  # False when Hmin is the one the shape class gives
    shape_class: Optional[str]  # the class that fixed the exponent; None when Hmin did
    warnings: List[str]
    step_m: float = STEP_M  # the level interval of the table


def _same(entered: float, on_sheet: float) -> bool:
    """The fields show 12 significant digits, so a sheet value with more digits counts as unchanged."""
    return math.isclose(entered, on_sheet, rel_tol=1e-9)


def curve_inputs(sheet: DamSheet, dam: Dam) -> CurveInputs:
    """The sheet's values, replaced by the dam's edits, with the dam's Hmin and shape class."""
    values = {}
    for name in _SHEET_FIELDS:
        edited = getattr(dam.curve, name)
        values[name] = getattr(sheet, name) if edited is None else edited
    return CurveInputs(h_min_m=dam.h_min_m, shape_class=dam.shape_class, **values)


def sheet_differences(sheet: DamSheet, inputs: CurveInputs) -> List[str]:
    """One line for each input that differs from the dam sheet, with the sheet's value."""
    lines = []
    for name in _SHEET_FIELDS:
        _, symbol, unit = FIELDS[name]
        used, on_sheet = getattr(inputs, name), getattr(sheet, name)
        if not _same(used, on_sheet):
            lines.append(f"{symbol} {used:g} {unit} (sheet: {on_sheet:g} {unit})")
    return lines


def validate_curve_entries(
    *, bed_elev_m, h_min_m, max_elev_m, crest_elev_m, active_vol_hm3, max_vol_hm3, shape_class
) -> CurveInputs:
    """Convert the entered texts. Hmin and the shape class may be blank (one of them is needed). Raises ValueError listing
    every problem."""
    entered = {
        "bed_elev_m": bed_elev_m,
        "h_min_m": h_min_m,
        "max_elev_m": max_elev_m,
        "crest_elev_m": crest_elev_m,
        "active_vol_hm3": active_vol_hm3,
        "max_vol_hm3": max_vol_hm3,
    }
    numbers, problems = {}, []
    for name, text in entered.items():
        if name == "h_min_m" and not cell_text(text):
            numbers[name] = None
            continue
        numbers[name] = parse_number(text)
        if numbers[name] is None:
            words, symbol, unit = FIELDS[name]
            problems.append(f"{words} ({symbol}, {unit}) must be a number, found {quote_cell(text)}.")
    shape = cell_text(shape_class) or None
    problems += check_shape(numbers["h_min_m"], shape)
    if not problems:
        problems = check_inputs(**numbers)
    if problems:
        raise ValueError("The curve inputs are not valid:\n" + "\n".join(f"- {problem}" for problem in problems))
    return CurveInputs(shape_class=shape, **numbers)


def parse_table_step(text) -> float:
    """The level interval of the table, in m, as entered in step 6 (a decimal comma is refused). Raises
    ValueError when it is blank, not a number, or not above 0."""
    step = parse_number(text)
    if step is None:
        raise ValueError(f"The level interval of the table (m) must be a number, found {quote_cell(text)}.")
    problems = check_step(step)
    if problems:
        raise ValueError("\n".join(problems))
    return step


def apply_curve_settings(project: Project, dam: Dam, sheet: DamSheet, **entered) -> bool:
    """Validate the entered texts and, only if they are all valid and saved, keep them on the dam: Hmin and the shape
    class as they are, and each sheet input only when it differs from the sheet. True if the curve changed (a new shape
    class is kept but does not change the curve while Hmin is given)."""
    inputs = validate_curve_entries(**entered)
    overrides = CurveOverrides(
        **{
            name: None if _same(getattr(inputs, name), getattr(sheet, name)) else getattr(inputs, name)
            for name in _SHEET_FIELDS
        }
    )
    previous = (dam.curve, dam.h_min_m, dam.shape_class)
    current = (overrides, inputs.h_min_m, inputs.shape_class)
    if current == previous:
        return False
    dam.curve, dam.h_min_m, dam.shape_class = current
    try:
        project.save()
    except OSError:
        dam.curve, dam.h_min_m, dam.shape_class = previous
        raise
    return _fixing(*current) != _fixing(*previous)


def _fixing(curve: CurveOverrides, h_min_m: Optional[float], shape_class: Optional[str]) -> tuple:
    """What fixes the curve: the edits, Hmin, and the shape class only while Hmin is blank."""
    return curve, h_min_m, shape_class if h_min_m is None else None


def compute_curve(
    inputs: CurveInputs, drainage_area_km2: Optional[float] = None, step_m: float = STEP_M
) -> CurveResult:
    """Fit the curve (B3.3) and make its table, at the level interval `step_m`, and warnings. The drainage area is the dam
    sheet's."""
    curve = fit_curve(
        bed_elev_m=inputs.bed_elev_m,
        max_elev_m=inputs.max_elev_m,
        crest_elev_m=inputs.crest_elev_m,
        active_vol_hm3=inputs.active_vol_hm3,
        max_vol_hm3=inputs.max_vol_hm3,
        h_min_m=inputs.h_min_m,
        shape_class=inputs.shape_class,
    )
    given = inputs.h_min_m is not None
    shape = None if given else inputs.shape_class
    return CurveResult(
        curve, curve_table(curve, step_m), given, shape, curve_warnings(curve, drainage_area_km2), step_m
    )


def compute_dam_curve(sheet: DamSheet, dam: Dam) -> CurveResult:
    """The dam's curve from its sheet and what step 6 kept on the dam."""
    return compute_curve(curve_inputs(sheet, dam), sheet.drainage_area_km2)


def write_reservoir_csv(result: CurveResult, folder) -> Path:
    """Write the curve table to `folder/reservoir_curve.csv` (UTF-8 with BOM, for Excel)."""
    path = Path(folder) / CSV_NAME
    result.table.to_csv(path, index=False, encoding="utf-8-sig")
    return path
