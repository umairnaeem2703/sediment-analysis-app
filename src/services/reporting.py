"""Charts of the reports (FR-M3-05); the M5 reporting service adds the workbook and `run.json`.

matplotlib lives here and never in `src/core` (B2). Figures are built with `Figure` rather than pyplot, so they hold no
global state, can be made off the Tk thread and can be embedded in the wizard.
"""

from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure

from src.core.wilcock import WATER_YEAR_COLUMN
from src.services.bedload import FLOW_M3_S, MASS_T

TREND_PNG = "bedload_trend.png"


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
