import sys
from pathlib import Path

import numpy as np
import pandas as pd


def resource_path(*parts: str) -> Path:
    """Resolve bundled data files for source runs and PyInstaller onedir/onefile."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent
    return base.joinpath(*parts)


def read_table(file_path: str) -> pd.DataFrame:
    """Load CSV or Excel using a case-insensitive suffix. CSV uses utf-8-sig."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported table format: {path.suffix}")


def load_raster_matrix(file_path: str) -> np.ndarray:
    """Load a headerless numeric CSV as a 2D raster array."""
    raster = np.loadtxt(file_path, delimiter=",", dtype=float)
    if raster.ndim == 1:
        raster = raster.reshape(1, -1)
    return raster
