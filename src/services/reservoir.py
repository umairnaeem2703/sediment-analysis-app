"""The measured reservoir curve of one dam (FR-M4-01, FR-M4-02, B3.3, D75, D76).

`validate_curve_sheet` and `load_curve_sheet` read a curve sheet: one row per level with its volume and surface area.
`import_curve_sheet` checks one and copies it into the project as the dam's curve. `parse_h_min` reads the entered
Hmin; `compute_curve`, `compute_dam_curve` and `apply_h_min` (which keeps it on the dam) put the table together with
it, refusing an Hmin outside the curve. `write_reservoir_csv` writes `reservoir_curve.csv` into a folder it is
given; the run folder itself belongs to the reporting service (M5).
"""

from pathlib import Path
from typing import List, NamedTuple

import pandas as pd

from src.core.reservoir import (
    AREA_KM2,
    ELEVATION_M,
    VOLUME_HM3,
    ReservoirCurve,
    build_curve,
    check_table,
)
from src.services.labels import CURVE_AREA, CURVE_ELEV, CURVE_SHEET, CURVE_VOL, match_columns
from src.services.project import Dam, Project
from src.services.regional import (
    Loaded,
    Problem,
    TableError,
    is_blank,
    parse_number,
    quote_cell,
    read_input,
)

CSV_NAME = "reservoir_curve.csv"
_COLUMNS = {CURVE_ELEV: ELEVATION_M, CURVE_VOL: VOLUME_HM3, CURVE_AREA: AREA_KM2}  # sheet label -> result column


class CurveResult(NamedTuple):
    curve: ReservoirCurve
    table: pd.DataFrame  # Elevation_m, Volume_hm3, Area_km2: the rows of the curve sheet
    warnings: List[str]


def validate_curve_sheet(df: pd.DataFrame, source: str) -> Loaded:
    """Check a curve sheet: every cell a number, levels and volumes rising, nothing below 0. Gives the table under the
    result columns (Elevation_m, Volume_hm3, Area_km2). Raises TableError naming every invalid cell or row."""
    table, warnings = match_columns(df, source, CURVE_SHEET)
    numbers, rows, problems = [], [], []
    for position, (_, record) in enumerate(table.iterrows()):
        if is_blank(record):
            continue
        row = position + 2
        values = {label: parse_number(record[label]) for label in CURVE_SHEET}
        for label, value in values.items():
            if value is None:
                message = f"row {row}: '{label}' must be a number, found {quote_cell(record[label])}."
                problems.append(Problem(message, ((row, label),)))
        numbers.append(values)
        rows.append(row)
    if problems:
        raise TableError(source, problems)
    curve = pd.DataFrame(numbers, columns=list(CURVE_SHEET), dtype=float).rename(columns=_COLUMNS)
    found = check_table(list(curve[ELEVATION_M]), list(curve[VOLUME_HM3]), list(curve[AREA_KM2]), rows)
    if found:
        raise TableError(source, [Problem(message) for message in found])
    return Loaded(curve, warnings)


def load_curve_sheet(path) -> Loaded:
    return validate_curve_sheet(read_input(path), Path(path).name)


def import_curve_sheet(project: Project, dam: Dam, path) -> Loaded:
    """Check a curve sheet and copy it into the project as the dam's curve. An unusable file raises and nothing is
    copied. Whether it holds Hmin is checked when the curve is computed."""
    loaded = load_curve_sheet(path)
    relative = project.import_file(path, f"inputs/curves/{dam.slug}_curve{Path(path).suffix.lower()}")
    previous = dam.curve_sheet
    dam.curve_sheet = relative
    try:
        project.save()
    except OSError:
        dam.curve_sheet = previous
        raise
    if previous and previous != relative:
        (project.folder / previous).unlink(missing_ok=True)
    return loaded


def parse_h_min(text) -> float:
    """The entered Hmin (m) as a number. Raises ValueError when it is blank or not a number."""
    value = parse_number(text)
    if value is None:
        raise ValueError(f"Hmin (m) must be a number, found {quote_cell(text)}.")
    return value


def compute_curve(table: pd.DataFrame, h_min_m: float, warnings=()) -> CurveResult:
    """The curve of a validated curve sheet with Hmin, and `warnings` (those of reading the curve sheet). Raises
    ValueError when Hmin is not inside the curve."""
    curve = build_curve(table[ELEVATION_M], table[VOLUME_HM3], table[AREA_KM2], h_min_m=h_min_m)
    return CurveResult(curve, curve.table(), list(warnings))


def _dam_curve(project: Project, dam: Dam, h_min_m: float) -> CurveResult:
    if not dam.curve_sheet:
        raise ValueError(f"{dam.name} has no reservoir curve sheet. Import it in step 6 (Reservoir curve).")
    table, warnings = load_curve_sheet(project.folder / dam.curve_sheet)
    return compute_curve(table, h_min_m, warnings)


def compute_dam_curve(project: Project, dam: Dam) -> CurveResult:
    """The dam's curve from the curve sheet in the project and the Hmin kept on the dam."""
    if dam.curve_sheet and dam.h_min_m is None:  # a missing curve sheet is named first, by _dam_curve
        raise ValueError(f"{dam.name} has no Hmin. Enter it in step 6 (Reservoir curve).")
    return _dam_curve(project, dam, dam.h_min_m)


def apply_h_min(project: Project, dam: Dam, text) -> CurveResult:
    """The dam's curve with the entered Hmin, which is kept on the dam only once the curve accepts it and it is saved."""
    h_min_m = parse_h_min(text)
    result = _dam_curve(project, dam, h_min_m)
    previous = dam.h_min_m
    dam.h_min_m = h_min_m
    try:
        project.save()
    except OSError:
        dam.h_min_m = previous
        raise
    return result


def write_reservoir_csv(result: CurveResult, folder) -> Path:
    """Write the curve table to `folder/reservoir_curve.csv` (UTF-8 with BOM, for Excel)."""
    path = Path(folder) / CSV_NAME
    result.table.to_csv(path, index=False, encoding="utf-8-sig")
    return path
