import sys
from pathlib import Path

import numpy as np
import pandas as pd


def resource_path(*parts: str) -> Path:
    """Resolve bundled data files for source runs and PyInstaller onedir/onefile."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        # Resolve to project root (two levels above src/utils)
        base = Path(__file__).resolve().parent.parent.parent
    return base.joinpath(*parts)


def read_table(file_path: str) -> pd.DataFrame:
    """Load CSV or Excel using a case-insensitive suffix. Handles UTF-8 and Turkish encodings (e.g. CP1254, ISO-8859-9)."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        encodings = ["utf-8-sig", "utf-8", "cp1254", "iso-8859-9", "windows-1252", "latin1"]
        last_exc = None
        for enc in encodings:
            try:
                df = pd.read_csv(path, encoding=enc)
                # Handle semicolon-delimited CSVs commonly exported by Turkish Excel
                if len(df.columns) == 1 and ";" in str(df.columns[0]):
                    try:
                        df_semi = pd.read_csv(path, encoding=enc, sep=";")
                        if len(df_semi.columns) > 1:
                            return df_semi
                    except Exception:
                        pass
                return df
            except (UnicodeDecodeError, UnicodeError) as exc:
                last_exc = exc
                continue
        if last_exc:
            raise last_exc
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported table format: {path.suffix}")



def load_raster_matrix(file_path: str) -> np.ndarray:
    """Load a headerless numeric CSV as a 2D raster array."""
    raster = np.loadtxt(file_path, delimiter=",", dtype=float)
    if raster.ndim == 1:
        raster = raster.reshape(1, -1)
    return raster
