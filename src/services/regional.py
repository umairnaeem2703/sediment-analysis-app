"""Load and validate the regional inputs: basin table, zonal means and dam sheets (FR-M1-03, FR-M1-05, FR-M1-06).

Row numbers in messages count the rows of the loaded table with the header as row 1, so the first data row
is row 2. Completely empty lines in a CSV are dropped on reading and are not counted.
Each `load_*` function reads a file; each `validate_*` function checks an in-memory table, so an edited
grid can be re-validated without a file.
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, NamedTuple, Optional, Tuple

import pandas as pd

from src.core.rusle import to_ascii_turkish, turkish_lower
from src.services.labels import (
    ACTIVE_VOL,
    AREA,
    AVG_FLOW,
    BASIN,
    BASIN_TABLE,
    BED_ELEV,
    CREST_ELEV,
    DAM,
    MAX_ELEV,
    MAX_VOL,
    MEAN,
    RIVER_LENGTH,
    SHEET_OPTIONAL,
    SHEET_REQUIRED,
    SHEET_SLOPE,
    SLOPE,
    SUBBASIN,
    TOP_ELEV,
    ZONAL,
    match_columns,
)
from src.utils.paths import read_table

CROSS_CHECK_TOLERANCE = 0.01
MAX_LISTED = 10


class Loaded(NamedTuple):
    """A validated table (or DamSheet) and the warnings raised while loading it."""

    data: Any
    warnings: List[str]


class Problem(NamedTuple):
    """One thing wrong with a table. `cells` are (row, column) pairs a grid can flag; rows count from the header = 1."""

    message: str
    cells: Tuple[Tuple[int, str], ...] = ()


class TableError(ValueError):
    """A table with invalid cells. The text lists them; `problems` locates them."""

    def __init__(self, source: str, problems: List[Problem]):
        listed = "\n".join(f"- {problem.message}" for problem in problems[:MAX_LISTED])
        more = f"\n- ... and {len(problems) - MAX_LISTED} more" if len(problems) > MAX_LISTED else ""
        super().__init__(f"{source}: {len(problems)} problem(s) found:\n{listed}{more}")
        self.source = source
        self.problems = problems


@dataclass(frozen=True)
class DamSheet:
    name: str
    bed_elev_m: float
    crest_elev_m: float
    max_elev_m: float
    active_vol_hm3: float
    max_vol_hm3: float
    drainage_area_km2: Optional[float] = None
    slope_m_per_m: Optional[float] = None
    river_length_km: Optional[float] = None
    top_elev_m: Optional[float] = None
    avg_flow_hm3_yr: Optional[float] = None


# DamSheet field -> its label on the dam sheet (the dam name and, when present, the drainage area are read as well)
_SHEET_REQUIRED = {
    "bed_elev_m": BED_ELEV,
    "crest_elev_m": CREST_ELEV,
    "max_elev_m": MAX_ELEV,
    "active_vol_hm3": ACTIVE_VOL,
    "max_vol_hm3": MAX_VOL,
}
_SHEET_OPTIONAL = {
    "drainage_area_km2": AREA,
    "slope_m_per_m": SHEET_SLOPE,
    "river_length_km": RIVER_LENGTH,
    "top_elev_m": TOP_ELEV,
    "avg_flow_hm3_yr": AVG_FLOW,
}


def name_key(text) -> str:
    """Turkish-aware comparison key: ASCII-folded, lowercase, single-spaced ('ÇUBUK  1' -> 'cubuk 1')."""
    return " ".join(to_ascii_turkish(turkish_lower(text)).split())


def read_input(path, dtype=None) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    try:
        return read_table(path, dtype=dtype)
    except Exception as exc:  # empty, corrupt, locked, undecodable or unsupported: always name the file
        raise ValueError(f"{path.name}: could not be read ({exc})") from exc


def cell_text(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def parse_number(value) -> Optional[float]:
    """The cell as a finite float, or None when it is blank or not a number."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
    else:
        try:
            number = float(cell_text(value))
        except ValueError:
            return None
    return number if math.isfinite(number) else None


def quote_cell(value) -> str:
    text = cell_text(value)
    return repr(text) if text else "an empty cell"


def is_blank(record) -> bool:
    return not any(cell_text(value) for value in record)


# --- basin table ------------------------------------------------------------------------------


def basin_grid(df: pd.DataFrame, source: str) -> Loaded:
    """The basin table's five columns under their canonical labels, every cell as text and not yet checked."""
    table, warnings = match_columns(df, source, BASIN_TABLE)
    grid = table.apply(lambda column: column.map(cell_text)).reset_index(drop=True)
    if all(is_blank(record) for _, record in grid.iterrows()):
        raise ValueError(f"{source}: no data rows found.")
    return Loaded(grid, warnings)


def read_basin_grid(path) -> Loaded:
    """Read a basin table for editing. Cell problems are allowed here; unreadable files and missing columns are not."""
    return basin_grid(read_input(path, dtype=str), Path(path).name)


def validate_basin_table(df: pd.DataFrame, source: str) -> Loaded:
    table, warnings = basin_grid(df, source)

    rows, problems, first_seen = [], [], {}
    for position, (_, record) in enumerate(table.iterrows()):
        if is_blank(record):
            continue
        row = position + 2
        entry = {}
        for column in (DAM, BASIN, SUBBASIN):
            entry[column] = cell_text(record[column])
            if not entry[column]:
                problems.append(Problem(f"row {row}: '{column}' is empty.", ((row, column),)))
        entry[AREA] = parse_number(record[AREA])
        if entry[AREA] is None or entry[AREA] <= 0:
            message = f"row {row}: '{AREA}' must be a number greater than 0, found {quote_cell(record[AREA])}."
            problems.append(Problem(message, ((row, AREA),)))
        entry[SLOPE] = parse_number(record[SLOPE])
        if entry[SLOPE] is None:
            message = f"row {row}: '{SLOPE}' must be a number, found {quote_cell(record[SLOPE])}."
            problems.append(Problem(message, ((row, SLOPE),)))
        if entry[DAM] and entry[SUBBASIN]:
            key = (name_key(entry[DAM]), name_key(entry[SUBBASIN]))
            if key in first_seen:
                message = (
                    f"rows {first_seen[key]} and {row}: sub-basin '{entry[SUBBASIN]}' appears twice "
                    f"for dam '{entry[DAM]}'."
                )
                problems.append(Problem(message, ((first_seen[key], SUBBASIN), (row, SUBBASIN))))
            else:
                first_seen[key] = row
        rows.append(entry)

    if problems:
        raise TableError(source, problems)
    return Loaded(pd.DataFrame(rows, columns=list(BASIN_TABLE)), warnings)


def load_basin_table(path) -> Loaded:
    """Read and validate a basin table the way the wizard does: through the grid, so both read the file alike."""
    grid = read_basin_grid(path)
    return Loaded(validate_basin_table(grid.data, Path(path).name).data, grid.warnings)


# --- zonal means ------------------------------------------------------------------------------


def validate_zonal_means(df: pd.DataFrame, source: str) -> Loaded:
    table, warnings = match_columns(df, source, ZONAL)

    kept, skipped = [], []
    for position, (_, record) in enumerate(table.iterrows()):
        name, mean = cell_text(record[SUBBASIN]), parse_number(record[MEAN])
        if name and mean is not None:
            kept.append((name, mean))
        elif name or cell_text(record[MEAN]):  # fully blank rows are not counted
            skipped.append(position + 2)
    if not kept:
        raise ValueError(f"{source}: no valid sub-basin MEAN values found.")

    if skipped:
        listed = ", ".join(str(row) for row in skipped[:MAX_LISTED]) + (", ..." if len(skipped) > MAX_LISTED else "")
        warnings.append(
            f"{source}: skipped {len(skipped)} row(s) with an empty sub-basin name or an empty or "
            f"non-numeric MEAN (rows {listed})."
        )
    return Loaded(pd.DataFrame(kept, columns=list(ZONAL)), warnings)


def load_zonal_means(path) -> Loaded:
    return validate_zonal_means(read_input(path), Path(path).name)


# --- dam sheet --------------------------------------------------------------------------------


def validate_dam_sheet(df: pd.DataFrame, source: str, basin_table: pd.DataFrame) -> Loaded:
    """Check one dam sheet and cross-check it against the dam's rows in a validated basin table."""
    table, warnings = match_columns(df, source, SHEET_REQUIRED, SHEET_OPTIONAL)

    records = [(position + 2, record) for position, (_, record) in enumerate(table.iterrows()) if not is_blank(record)]
    if len(records) != 1:
        raise ValueError(f"{source}: a dam sheet must hold exactly one dam row; found {len(records)}.")
    row, record = records[0]

    dams = {}
    for name in basin_table[DAM]:
        dams.setdefault(name_key(name), name)  # the table's first spelling names the dam
    sheet_name = cell_text(record[DAM])
    if name_key(sheet_name) not in dams:
        raise ValueError(
            f"{source}: dam '{sheet_name}' is not in the basin table (dams: {', '.join(sorted(set(dams.values())))})."
        )
    dam = dams[name_key(sheet_name)]

    values, problems = {}, []
    for field, label in {**_SHEET_REQUIRED, **_SHEET_OPTIONAL}.items():
        if label not in table.columns:
            values[field] = None
            continue
        raw = record[label]
        values[field] = parse_number(raw)
        if values[field] is None and (field in _SHEET_REQUIRED or cell_text(raw)):
            problems.append(
                Problem(f"row {row}: '{label}' must be a number, found {quote_cell(raw)}.", ((row, label),))
            )
    if problems:
        raise TableError(source, problems)

    own = basin_table[basin_table[DAM].map(name_key) == name_key(dam)]
    table_area = float(own[AREA].sum())
    area = values["drainage_area_km2"]
    if area is not None and abs(area - table_area) > CROSS_CHECK_TOLERANCE * table_area:
        warnings.append(
            f"{source}: drainage area {area:g} km2 differs from the basin table's {table_area:g} km2 by more than 1%."
        )
    slope = values["slope_m_per_m"]
    table_slope = float((own[AREA] * own[SLOPE]).sum()) / table_area
    if slope is not None and abs(slope - table_slope) > CROSS_CHECK_TOLERANCE * abs(table_slope):
        warnings.append(
            f"{source}: slope {slope:g} m/m differs from the basin table's area-weighted {table_slope:.4g} m/m "
            f"by more than 1%."
        )
    return Loaded(DamSheet(name=dam, **values), warnings)


def load_dam_sheet(path, basin_table: pd.DataFrame) -> Loaded:
    return validate_dam_sheet(read_input(path), Path(path).name, basin_table)
