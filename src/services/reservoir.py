"""The measured reservoir curve of one dam (FR-M4-01, FR-M4-02, B3.3, D75).

`validate_curve_sheet` and `load_curve_sheet` read a curve sheet: one row per level with its volume and surface area.
`import_curve_sheet` checks one and copies it into the project as the dam's curve. `compute_curve` and
`compute_dam_curve` put the table together with the dam sheet, refusing a dam sheet the curve does not cover, and give the
warnings. `write_reservoir_csv` writes `reservoir_curve.csv` into a folder it is given; the run folder itself belongs
to the reporting service (M5).
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
    curve_warnings,
)
from src.services.labels import CURVE_AREA, CURVE_ELEV, CURVE_SHEET, CURVE_VOL, match_columns
from src.services.project import Dam, Project
from src.services.regional import (
    DamSheet,
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
    copied. Whether it covers the dam sheet is checked when the curve is computed."""
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


def compute_curve(table: pd.DataFrame, sheet: DamSheet, warnings=()) -> CurveResult:
    """The curve of a validated curve sheet with the values of the dam sheet, and its warnings: `warnings` (those of
    reading the curve sheet) and the plausibility warning. Raises ValueError when the curve does not cover the dam
    sheet."""
    curve = build_curve(
        table[ELEVATION_M],
        table[VOLUME_HM3],
        table[AREA_KM2],
        bed_elev_m=sheet.bed_elev_m,
        max_elev_m=sheet.max_elev_m,
        crest_elev_m=sheet.crest_elev_m,
        active_vol_hm3=sheet.active_vol_hm3,
        max_vol_hm3=sheet.max_vol_hm3,
    )
    return CurveResult(curve, curve.table(), [*warnings, *curve_warnings(curve, sheet.drainage_area_km2)])


def compute_dam_curve(project: Project, sheet: DamSheet, dam: Dam) -> CurveResult:
    """The dam's curve from the curve sheet in the project and its dam sheet."""
    if not dam.curve_sheet:
        raise ValueError(f"{dam.name} has no reservoir curve sheet. Import it in step 6 (Reservoir curve).")
    table, warnings = load_curve_sheet(project.folder / dam.curve_sheet)
    return compute_curve(table, sheet, warnings)


def write_reservoir_csv(result: CurveResult, folder) -> Path:
    """Write the curve table to `folder/reservoir_curve.csv` (UTF-8 with BOM, for Excel)."""
    path = Path(folder) / CSV_NAME
    result.table.to_csv(path, index=False, encoding="utf-8-sig")
    return path
