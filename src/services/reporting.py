"""Charts of the reports (FR-M3-05); the M5 reporting service adds the workbook and `run.json`.

matplotlib lives here and never in `src/core` (B2). Figures are built with `Figure` rather than pyplot, so they hold no
global state, can be made off the Tk thread and can be embedded in the wizard.
"""

from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure

from src.core.reservoir import AREA_KM2, ELEVATION_M, VOLUME_HM3
from src.core.wilcock import WATER_YEAR_COLUMN
from src.services.bedload import FLOW_M3_S, MASS_T
from src.services.reservoir import CurveResult

TREND_PNG = "bedload_trend.png"
CURVE_PNG = "reservoir_curve.png"


def bedload_trend_figure(table: pd.DataFrame) -> Figure:
    """Annual mean flow and annual bedload mass against the year, from a `BedloadResult.table`."""
    if table is None or table.empty:
        raise ValueError("The bedload table is empty. Cannot generate the chart.")
    key = table.columns[0]
    years = table[key]

    figure = Figure(figsize=(10, 6), layout="tight")
    flow_axis = figure.subplots()
    flow_line = flow_axis.plot(years, table[FLOW_M3_S], color="blue", marker="o", label="Mean Flow")[0]
    flow_axis.set_xlabel("Water Year (Oct–Sep)" if key == WATER_YEAR_COLUMN else "Year", fontweight="bold")
    flow_axis.set_ylabel("Annual Mean Flow (m³/s)", color="blue", fontweight="bold")
    flow_axis.tick_params(axis="y", labelcolor="blue")
    flow_axis.grid(True, linestyle="--", alpha=0.6)

    mass_axis = flow_axis.twinx()
    mass_line = mass_axis.plot(years, table[MASS_T], color="red", marker="s", label="Bed Load")[0]
    mass_axis.set_ylabel("Annual Bed Load (t/yr)", color="red", fontweight="bold")
    mass_axis.tick_params(axis="y", labelcolor="red")

    flow_axis.legend([flow_line, mass_line], [flow_line.get_label(), mass_line.get_label()], loc="upper right")
    flow_axis.set_title("Annual Flow vs. Bed Load Trends", fontweight="bold", pad=15)
    return figure


def write_bedload_trend(table: pd.DataFrame, folder) -> Path:
    """Write the trend chart to `folder/bedload_trend.png`."""
    path = Path(folder) / TREND_PNG
    bedload_trend_figure(table).savefig(path, dpi=150)
    return path


def reservoir_curve_figure(result: CurveResult) -> Figure:
    """Volume and surface area against the level, with Hmin and Hmax marked, from a `CurveResult`."""
    table, curve = result.table, result.curve
    figure = Figure(figsize=(10, 6), layout="tight")
    volume_axis = figure.subplots()
    volume_line = volume_axis.plot(table[ELEVATION_M], table[VOLUME_HM3], color="blue", label="Volume")[0]
    volume_axis.set_xlabel("Elevation (m)", fontweight="bold")
    volume_axis.set_ylabel("Volume (hm³)", color="blue", fontweight="bold")
    volume_axis.tick_params(axis="y", labelcolor="blue")
    volume_axis.grid(True, linestyle="--", alpha=0.6)
    h_min_line = volume_axis.axvline(curve.h_min_m, color="green", linestyle="--", label="Hmin")
    h_max_line = volume_axis.axvline(curve.max_elev_m, color="black", linestyle="--", label="Hmax")

    area_axis = volume_axis.twinx()
    area_line = area_axis.plot(table[ELEVATION_M], table[AREA_KM2], color="red", label="Surface area")[0]
    area_axis.set_ylabel("Surface area (km²)", color="red", fontweight="bold")
    area_axis.tick_params(axis="y", labelcolor="red")

    lines = [volume_line, area_line, h_min_line, h_max_line]
    volume_axis.legend(lines, [line.get_label() for line in lines], loc="upper left")
    volume_axis.set_title("Reservoir Elevation-Volume Curve", fontweight="bold", pad=15)
    return figure


def write_reservoir_curve(result: CurveResult, folder) -> Path:
    """Write the curve chart to `folder/reservoir_curve.png`."""
    path = Path(folder) / CURVE_PNG
    reservoir_curve_figure(result).savefig(path, dpi=150)
    return path
