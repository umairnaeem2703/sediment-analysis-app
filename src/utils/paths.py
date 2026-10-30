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


def read_table(file_path: str, dtype=None) -> pd.DataFrame:
    """Load CSV or Excel using a case-insensitive suffix. Handles UTF-8 and Turkish encodings (e.g. CP1254, ISO-8859-9).

    `dtype=str` keeps every cell as written (leading zeros, trailing zeros) instead of letting pandas parse numbers.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        encodings = ["utf-8-sig", "utf-8", "cp1254", "iso-8859-9", "windows-1252", "latin1"]
        last_exc = None
        for enc in encodings:
            try:
                df = pd.read_csv(path, encoding=enc, dtype=dtype)
                # Handle semicolon-delimited CSVs commonly exported by Turkish Excel
                if len(df.columns) == 1 and ";" in str(df.columns[0]):
                    try:
                        df_semi = pd.read_csv(path, encoding=enc, sep=";", dtype=dtype)
                    except Exception:
                        df_semi = None
                    if df_semi is not None and len(df_semi.columns) > 1:
                        return _without_shifted_columns(df_semi, path)
                return _without_shifted_columns(df, path)
            except (UnicodeDecodeError, UnicodeError) as exc:
                last_exc = exc
                continue
        if last_exc:
            raise last_exc
        return pd.read_csv(path, dtype=dtype)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, dtype=dtype)
    raise ValueError(f"Unsupported table format: {path.suffix}")
