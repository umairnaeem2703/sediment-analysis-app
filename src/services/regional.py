"""Load and validate the regional inputs: basin table, zonal means and dam sheets (FR-M1-03, FR-M1-05, FR-M1-06).

Row numbers in messages count the rows of the loaded table with the header as row 1, so the first data row
is row 2. Completely empty lines in a CSV are dropped on reading and are not counted.
Each `load_*` function reads a file; each `validate_*` function checks an in-memory table, so an edited
grid can be re-validated without a file.
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, NamedTuple, Optional

import pandas as pd

from src.core.rusle import find_basin_table_columns, normalize_header, to_ascii_turkish, turkish_lower
from src.utils.paths import read_table

CROSS_CHECK_TOLERANCE = 0.01
MAX_LISTED = 10

DAM, BASIN, SUBBASIN = "Dam Name", "Basin Name", "Sub-basin Name"
AREA, SLOPE = "Drainage Area (km2)", "Main Waterway Slope"
BASIN_COLUMNS = {"dam": DAM, "basin": BASIN, "subbasin": SUBBASIN, "area": AREA, "slope": SLOPE}
ZONAL_COLUMNS = [SUBBASIN, "MEAN"]


class Loaded(NamedTuple):
    """A validated table (or DamSheet) and the warnings raised while loading it."""

    data: Any
    warnings: List[str]


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


# DamSheet field -> (header shown in messages, accepted headers after normalize_header)
_SHEET_REQUIRED = {
    "bed_elev_m": ("Bot Elev of River", ("botelevofriver",)),
    "crest_elev_m": ("Cret Elev", ("cretelev", "crestelev")),
    "max_elev_m": ("Max Res. Elev", ("maxreselev",)),
    "active_vol_hm3": ("Active Vol.", ("activevol",)),
    "max_vol_hm3": ("Max Vol.", ("maxvol",)),
}
_SHEET_OPTIONAL = {
    "slope_m_per_m": ("Avg. Slope %", ("avgslope%", "avgslope")),
    "river_length_km": ("Longest River Length (km)", ("longestriverlength(km)", "longestriverlength")),
    "top_elev_m": ("Top Elev of River", ("topelevofriver",)),
    "avg_flow_hm3_yr": ("Avg. Flow", ("avgflow",)),
}


def name_key(text) -> str:
    """Turkish-aware comparison key: ASCII-folded, lowercase, single-spaced ('ÇUBUK  1' -> 'cubuk 1')."""
    return " ".join(to_ascii_turkish(turkish_lower(text)).split())


def _read(path) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    try:
        return read_table(path)
    except Exception as exc:  # empty, corrupt, locked, undecodable or unsupported: always name the file
        raise ValueError(f"{path.name}: could not be read ({exc})") from exc


def _text(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _number(value) -> Optional[float]:
    """The cell as a finite float, or None when it is blank or not a number."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
    else:
        try:
            number = float(_text(value).replace(",", "."))
        except ValueError:
            return None
    return number if math.isfinite(number) else None


def _shown(value) -> str:
    text = _text(value)
    return repr(text) if text else "an empty cell"


def _problems_error(source: str, problems: List[str]) -> ValueError:
    listed = "\n".join(f"- {problem}" for problem in problems[:MAX_LISTED])
    more = f"\n- ... and {len(problems) - MAX_LISTED} more" if len(problems) > MAX_LISTED else ""
    return ValueError(f"{source}: {len(problems)} problem(s) found:\n{listed}{more}")


def _missing_columns_error(source: str, missing: List[str], df: pd.DataFrame) -> ValueError:
    present = ", ".join(str(column) for column in df.columns)
    return ValueError(f"{source}: required column(s) not found: {', '.join(missing)}. Columns present: {present}.")


def _is_blank(record) -> bool:
    return not any(_text(value) for value in record)


# --- basin table ------------------------------------------------------------------------------


def validate_basin_table(df: pd.DataFrame, source: str) -> Loaded:
    found = find_basin_table_columns(df.columns)
    missing = [label for key, label in BASIN_COLUMNS.items() if found[key] is None]
    if missing:
        raise _missing_columns_error(source, missing, df)
    table = df[[found[key] for key in BASIN_COLUMNS]]
    table.columns = list(BASIN_COLUMNS.values())

    rows, problems, first_seen = [], [], {}
    for position, (_, record) in enumerate(table.iterrows()):
        if _is_blank(record):
            continue
        row = position + 2
        entry = {}
        for column in (DAM, BASIN, SUBBASIN):
            entry[column] = _text(record[column])
            if not entry[column]:
                problems.append(f"row {row}: '{column}' is empty.")
        entry[AREA] = _number(record[AREA])
        if entry[AREA] is None or entry[AREA] <= 0:
            problems.append(f"row {row}: '{AREA}' must be a number greater than 0, found {_shown(record[AREA])}.")
        entry[SLOPE] = _number(record[SLOPE])
        if entry[SLOPE] is None:
            problems.append(f"row {row}: '{SLOPE}' must be a number, found {_shown(record[SLOPE])}.")
        if entry[DAM] and entry[SUBBASIN]:
            key = (name_key(entry[DAM]), name_key(entry[SUBBASIN]))
            if key in first_seen:
                problems.append(
                    f"rows {first_seen[key]} and {row}: sub-basin '{entry[SUBBASIN]}' appears twice "
                    f"for dam '{entry[DAM]}'."
                )
            else:
                first_seen[key] = row
        rows.append(entry)

    if problems:
        raise _problems_error(source, problems)
    if not rows:
        raise ValueError(f"{source}: no data rows found.")
    return Loaded(pd.DataFrame(rows, columns=list(BASIN_COLUMNS.values())), [])


def load_basin_table(path) -> Loaded:
    return validate_basin_table(_read(path), Path(path).name)


# --- zonal means ------------------------------------------------------------------------------


def validate_zonal_means(df: pd.DataFrame, source: str) -> Loaded:
    name_column = find_basin_table_columns(df.columns)["subbasin"]
    mean_column = next((c for c in df.columns if normalize_header(c) in ("mean", "ortalama")), None)
    present = ", ".join(str(column) for column in df.columns)
    if mean_column is None:
        raise ValueError(f"{source}: column MEAN (or ORTALAMA) not found. Columns present: {present}.")
    if name_column is None:
        raise ValueError(
            f"{source}: sub-basin name column not found (for example 'Sub-basin' or 'Alt Havza'). "
            f"Columns present: {present}."
        )

    kept, skipped = [], []
    for position, (_, record) in enumerate(df.iterrows()):
        name, mean = _text(record[name_column]), _number(record[mean_column])
        if name and mean is not None:
            kept.append((name, mean))
        elif name or _text(record[mean_column]):  # fully blank rows are not counted
            skipped.append(position + 2)
    if not kept:
        raise ValueError(f"{source}: no valid sub-basin MEAN values found.")

    warnings = []
    if skipped:
        listed = ", ".join(str(row) for row in skipped[:MAX_LISTED]) + (", ..." if len(skipped) > MAX_LISTED else "")
        warnings.append(
            f"{source}: skipped {len(skipped)} row(s) with an empty sub-basin name or an empty or "
            f"non-numeric MEAN (rows {listed})."
        )
    return Loaded(pd.DataFrame(kept, columns=ZONAL_COLUMNS), warnings)


def load_zonal_means(path) -> Loaded:
    return validate_zonal_means(_read(path), Path(path).name)


# --- dam sheet --------------------------------------------------------------------------------


def validate_dam_sheet(df: pd.DataFrame, source: str, basin_table: pd.DataFrame) -> Loaded:
    """Check one dam sheet and cross-check it against the dam's rows in a validated basin table."""
    normalized = {normalize_header(column): column for column in df.columns}
    found = find_basin_table_columns(df.columns)

    def locate(aliases):
        return next((normalized[alias] for alias in aliases if alias in normalized), None)

    columns = {field: locate(aliases) for field, (_, aliases) in {**_SHEET_REQUIRED, **_SHEET_OPTIONAL}.items()}
    columns["name"], columns["drainage_area_km2"] = found["dam"], found["area"]
    missing = ([DAM] if columns["name"] is None else []) + [
        label for field, (label, _) in _SHEET_REQUIRED.items() if columns[field] is None
    ]
    if missing:
        raise _missing_columns_error(source, missing, df)

    records = [(position + 2, record) for position, (_, record) in enumerate(df.iterrows()) if not _is_blank(record)]
    if len(records) != 1:
        raise ValueError(f"{source}: a dam sheet must hold exactly one dam row; found {len(records)}.")
    row, record = records[0]

    dams = {}
    for name in basin_table[DAM]:
        dams.setdefault(name_key(name), name)  # the table's first spelling names the dam
    sheet_name = _text(record[columns["name"]])
    if name_key(sheet_name) not in dams:
        raise ValueError(
            f"{source}: dam '{sheet_name}' is not in the basin table (dams: {', '.join(sorted(set(dams.values())))})."
        )
    dam = dams[name_key(sheet_name)]

    values, problems = {}, []
    for field, (label, _) in {**_SHEET_REQUIRED, **_SHEET_OPTIONAL, "drainage_area_km2": (AREA, ())}.items():
        column = columns[field]
        if column is None:
            values[field] = None
            continue
        raw = record[column]
        values[field] = _number(raw)
        if values[field] is None and (field in _SHEET_REQUIRED or _text(raw)):
            problems.append(f"row {row}: '{label}' must be a number, found {_shown(raw)}.")
    if problems:
        raise _problems_error(source, problems)

    warnings = []
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
    return validate_dam_sheet(_read(path), Path(path).name, basin_table)
