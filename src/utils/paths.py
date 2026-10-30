import sys
from pathlib import Path

import pandas as pd


def resource_path(*parts: str) -> Path:
    """Resolve bundled data files for source runs and PyInstaller onedir/onefile."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        # Resolve to project root (two levels above src/utils)
        base = Path(__file__).resolve().parent.parent.parent
    return base.joinpath(*parts)


def _without_shifted_columns(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    """pandas makes the first column the row index when every data row has one more field than the header (for example
    a decimal comma in a comma-separated file), which would shift every column. Refuse such a file."""
    if not isinstance(df.index, pd.RangeIndex):
        raise ValueError(
            f"{path.name}: the rows have more values than the header has columns. "
            "Check for a comma used as a decimal point or as a thousands separator, or a separator at the end of every row."
        )
    return df


_ENCODINGS = ("utf-8-sig", "cp1254", "iso-8859-9", "windows-1252")  # utf-8-sig also reads utf-8 without a BOM


def _read_csv(path: Path, encoding: str, dtype) -> pd.DataFrame:
    df = pd.read_csv(path, encoding=encoding, dtype=dtype)
    # Handle semicolon-delimited CSVs commonly exported by Turkish Excel
    if len(df.columns) == 1 and ";" in str(df.columns[0]):
        try:
            df_semi = pd.read_csv(path, encoding=encoding, sep=";", dtype=dtype)
        except Exception:
            df_semi = None
        if df_semi is not None and len(df_semi.columns) > 1:
            return _without_shifted_columns(df_semi, path)
    return _without_shifted_columns(df, path)


def read_table(file_path: str, dtype=None) -> pd.DataFrame:
    """Load CSV or Excel using a case-insensitive suffix. Handles UTF-8 and Turkish encodings (e.g. CP1254, ISO-8859-9).

    `dtype=str` keeps every cell as written (leading zeros, trailing zeros) instead of letting pandas parse numbers.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        for encoding in _ENCODINGS:
            try:
                return _read_csv(path, encoding, dtype)
            except UnicodeError:
                continue
        return _read_csv(path, "latin1", dtype)  # latin1 decodes every byte, so the last try cannot fail on encoding
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, dtype=dtype)
    raise ValueError(f"Unsupported table format: {path.suffix}")
