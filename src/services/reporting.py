"""Charts of the reports (FR-M3-05, FR-M5-02); the workbook and `run.json` are written by `run_export.py`.

matplotlib lives here and never in `src/core` (B2). Figures are built with `Figure` rather than pyplot, so they hold no
global state, can be made off the Tk thread and can be embedded in the wizard.
"""

from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure

from src.core.projection import RATE_NAMES, YEAR
from src.core.reservoir import AREA_KM2, ELEVATION_M, VOLUME_HM3
from src.core.wilcock import WATER_YEAR_COLUMN
from src.services.bedload import FLOW_M3_S, MASS_T
from src.services.integration import TOTAL_HM3, IntegrationResult
from src.services.reservoir import CurveResult

TREND_PNG = "bedload_trend.png"
CURVE_PNG = "reservoir_curve.png"
ANNUAL_PNG = "annual_volume.png"
PROJECTION_PNG = "projection.png"


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


def projection_figure(result: IntegrationResult) -> Figure:
    """The cumulative sediment volume against the year at the three rates, with the dead volume (Hmin) marked."""
    figure = Figure(figsize=(10, 6), layout="tight")
    axis = figure.subplots()
    history = result.accumulation
    if not history.empty:  # the volume at the end of each year, which is the volume at the start of the next
        years = [result.commissioning_year, *(history["Year"] + 1)]
        axis.plot(years, [0.0, *history["Cumulative_hm3"]], color="gray", label="Accumulated to date")
    colors = {"Mean": "blue", "Min": "green", "Max": "red"}
    for name in RATE_NAMES:
        label = f"{name} rate ({result.rates[name]:,.2f} hm³/yr)"
        axis.plot(
            result.projection["Year"], result.projection[f"Cumulative_{name}_hm3"], color=colors[name], label=label
        )
        reached = result.lifespans[name]
        if reached.status == YEAR and reached.year <= result.projection["Year"].iloc[-1]:
            axis.plot(reached.year, result.dead_vol_hm3, color=colors[name], marker="o")
    axis.axhline(
        result.dead_vol_hm3,
        color="black",
        linestyle="--",
        label=f"Dead volume ({result.dead_vol_hm3:,.2f} hm³, Hmin {result.h_min_m:.2f} m)",
    )
    axis.set_xlabel("Year", fontweight="bold")
    axis.set_ylabel("Cumulative sediment (hm³)", fontweight="bold")
    axis.grid(True, linestyle="--", alpha=0.6)
    axis.legend(loc="upper left")
    axis.set_title("Sediment Accumulation and Lifespan", fontweight="bold", pad=15)
    return figure


def annual_volume_figure(result: IntegrationResult) -> Figure:
    """The sediment that stays in the reservoir each year of the record, with the mean, minimum and maximum marked."""
    annual = result.annual
    figure = Figure(figsize=(10, 6), layout="tight")
    axis = figure.subplots()
    axis.bar(annual[result.year_column], annual[TOTAL_HM3], color="steelblue", label="Annual total")
    colors = {"Mean": "blue", "Min": "green", "Max": "red"}
    for name in RATE_NAMES:
        axis.axhline(
            result.rates[name],
            color=colors[name],
            linestyle="--",
            label=f"{name} ({result.rates[name]:,.4f} hm³/yr)",
        )
    axis.set_xlabel("Water Year (Oct–Sep)" if result.year_column == WATER_YEAR_COLUMN else "Year", fontweight="bold")
    axis.set_ylabel("Sediment volume (hm³/yr)", fontweight="bold")
    axis.grid(True, axis="y", linestyle="--", alpha=0.6)
    axis.legend(loc="upper right")
    axis.set_title("Annual Sediment Volume in the Reservoir", fontweight="bold", pad=15)
    return figure


def write_annual_volume(result: IntegrationResult, folder) -> Path:
    """Write the annual volume chart to `folder/annual_volume.png`."""
    path = Path(folder) / ANNUAL_PNG
    annual_volume_figure(result).savefig(path, dpi=150)
    return path


def write_projection(result: IntegrationResult, folder) -> Path:
    """Write the projection chart to `folder/projection.png`."""
    path = Path(folder) / PROJECTION_PNG
    projection_figure(result).savefig(path, dpi=150)
    return path


def write_reservoir_curve(result: CurveResult, folder) -> Path:
    """Write the curve chart to `folder/reservoir_curve.png`."""
    path = Path(folder) / CURVE_PNG
    reservoir_curve_figure(result).savefig(path, dpi=150)
    return path
