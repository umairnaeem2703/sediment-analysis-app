"""The column labels of every input file, one canonical label per column, matched by one rule (D67).

A header matches a label when the two are equal after `fold`: case, Turkish letters, spaces, `.` `:` `%` and the
superscripts `²` `³` do not matter. No other spelling and no other language is accepted. `match_columns` is the one
function that reads a file's header; it hands back the table under the canonical labels, so everything after it
(`src/core` included) deals only with canonical names. `INPUT_FORMAT.md` is the same table, written for the user.
"""

from typing import List, Sequence, Tuple

import pandas as pd

from src.core.monthly_flow_preprocessor import WATER_YEAR_MONTHS, YEAR_HEADER
from src.core.rusle import to_ascii_turkish, turkish_lower
from src.core.wilcock import DATE_COLUMN, FLOW_COLUMN, WATER_YEAR_COLUMN

# Basin table (master_yield.csv); the sub-basin label is also the join key of the zonal means.
DAM, BASIN, SUBBASIN = "Dam Name", "Basin Name", "Sub-basin Name"
AREA, SLOPE = "Drainage Area (km2)", "Main Waterway Slope"
BASIN_TABLE = (DAM, BASIN, SUBBASIN, AREA, SLOPE)

MEAN = "MEAN"
ZONAL = (SUBBASIN, MEAN)

# Dam sheet; the dam name and the drainage area are shared with the basin table.
BED_ELEV, CREST_ELEV, MAX_ELEV = "Bot Elev of River", "Cret Elev", "Max Res. Elev"
ACTIVE_VOL, MAX_VOL = "Active Vol.", "Max Vol."
SHEET_SLOPE, RIVER_LENGTH, TOP_ELEV, AVG_FLOW = (
    "Avg. Slope",
    "Longest River Length (km)",
    "Top Elev of River",
    "Avg. Flow",
)
SHEET_REQUIRED = (DAM, BED_ELEV, CREST_ELEV, MAX_ELEV, ACTIVE_VOL, MAX_VOL)
SHEET_OPTIONAL = (AREA, SHEET_SLOPE, RIVER_LENGTH, TOP_ELEV, AVG_FLOW)

# Grain fractions: tau_ri and bi are computed and only cross-checked against a supplied column (D36).
FRACTIONS_REQUIRED = ("di", "Fi")
FRACTIONS_OPTIONAL = ("bi", "tau_ri")

# Daily flow, and the DSİ monthly table in the layout the DSİ publishes (Turkish).
DAILY_FLOW = (DATE_COLUMN, FLOW_COLUMN)
DAILY_FLOW_OPTIONAL = (WATER_YEAR_COLUMN,)
DSI_MONTHS = tuple(name for name, _ in WATER_YEAR_MONTHS)
DSI_REQUIRED = (YEAR_HEADER, *DSI_MONTHS)
DSI_OPTIONAL = ("TOP.",)

_DROPPED = str.maketrans("", "", ".:%")


def fold(text) -> str:
    """A header for comparison: 'Drainage  Area (km²)' and 'drainage area (km2)' fold to the same text."""
    folded = to_ascii_turkish(turkish_lower(text)).replace("²", "2").replace("³", "3")
    return "".join(folded.split()).translate(_DROPPED)


def missing_columns_error(source: str, missing: Sequence[str], df: pd.DataFrame) -> ValueError:
    present = ", ".join(str(column) for column in df.columns)
    return ValueError(f"{source}: required column(s) not found: {', '.join(missing)}. Columns present: {present}.")


def _is_empty_unnamed(df: pd.DataFrame, column) -> bool:
    """A column left over from a trailing delimiter: no name and no cell."""
    return str(column).startswith("Unnamed:") and bool(df[column].isna().all())


def match_columns(
    df: pd.DataFrame, source: str, required: Sequence[str], optional: Sequence[str] = ()
) -> Tuple[pd.DataFrame, List[str]]:
    """The columns of `df` that carry a label of this format, renamed to the canonical labels and in canonical order,
    and the warnings: one when columns outside the format are ignored. A missing required label is an error that names
    the canonical labels and the columns the file has; so are two headers that mean the same label."""
    wanted = {fold(label): label for label in (*required, *optional)}
    found = {}
    for column in df.columns:
        label = wanted.get(fold(column))
        if label is None:
            continue
        if label in found:
            raise ValueError(f"{source}: columns '{found[label]}' and '{column}' both mean '{label}'.")
        found[label] = column
    missing = [label for label in required if label not in found]
    if missing:
        raise missing_columns_error(source, missing, df)

    kept = [label for label in (*required, *optional) if label in found]
    table = df[[found[label] for label in kept]].copy()
    table.columns = kept
    used = set(found.values())
    ignored = [str(column) for column in df.columns if column not in used and not _is_empty_unnamed(df, column)]
    warnings = [f"{source}: ignored column(s) {', '.join(ignored)}."] if ignored else []
    return table, warnings


def is_monthly_flow_table(df: pd.DataFrame) -> bool:
    """True if the table looks like a DSİ monthly table rather than a Date/Flow daily series.

    Deliberately broad: a malformed DSİ file (for example a missing month column) still routes to the DSİ reader, which
    reports the specific missing labels instead of a generic Date/Flow error.
    """
    if df is None or df.empty:
        return False
    names = {fold(column) for column in df.columns}
    if fold(DATE_COLUMN) in names:
        return False
    return any(fold(label) in names for label in DSI_REQUIRED)
