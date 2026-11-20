"""Load and validate the regional inputs: basin table and zonal means (FR-M1-03, FR-M1-06).

Row numbers in messages count the rows of the loaded table with the header as row 1, so the first data row
is row 2. Completely empty lines in a CSV are dropped on reading and are not counted.
Each `load_*` function reads a file; each `validate_*` function checks an in-memory table, so an edited
grid can be re-validated without a file.
"""

import math
from pathlib import Path
from typing import Any, List, NamedTuple, Optional, Tuple

import pandas as pd

from src.core.text import name_key
from src.services.labels import (
    AREA,
    BASIN,
    BASIN_TABLE,
    DAM,
    MEAN,
    SLOPE,
    SUBBASIN,
    ZONAL,
    match_columns,
)
from src.utils.log import get_logger
from src.utils.paths import read_table

MAX_LISTED = 10


class Loaded(NamedTuple):
    """A validated table and the warnings raised while loading it."""

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


def read_input(path, dtype=None) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    try:
        return read_table(path, dtype=dtype)
    except Exception as exc:  # empty, corrupt, locked, undecodable or unsupported: always name the file
        get_logger().warning("%s could not be read.", path.name, exc_info=exc)
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
