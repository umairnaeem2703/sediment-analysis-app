from dataclasses import dataclass
import math
from typing import List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.core.rusle import normalize_header

SECONDS_PER_YEAR = 365.25 * 24.0 * 3600.0
YEAR_COLUMN = "Year"
WATER_YEAR_COLUMN = "Water_Year"  # Oct (Y-1) to Sep (Y), carried by DSI-derived daily series
PHI_BREAK = 1.35
FLOW_COLUMN_LABEL = "Annual Average Flow (m3/s)"
BEDLOAD_COLUMN_LABEL = "Annual Average Bed Load (metric tons/year)"


@dataclass
class HydraulicParameters:
    tau: float
    u_star: float


@dataclass
class FractionRecord:
    di: float
    Fi: float
    bi: float
    tau_ri: float


class FractionalModel:
    def __init__(self):
        self.g = 9.81
        self.rho_w = 1000.0
        self.rho_s = 2650.0
        self.s = self.rho_s / self.rho_w

        self.d50 = 0.02
        self.f_s = 0.10
        self.manning_n = 0.05
        self.bed_width = 50.0
        self.depth = 0.5
        self.fractions = []
        self._fi = np.array([], dtype=float)
        self._tau_ri = np.array([], dtype=float)

    def calculate_hydraulics(self, q_flow: float) -> Tuple[float, float]:
        if q_flow <= 0:
            return 0.0, 0.0
        area = self.bed_width * self.depth
        velocity = q_flow / area
        tau = (self.rho_w * self.g * (self.manning_n ** 2) * (velocity ** 2)) / math.pow(self.depth, 1.0 / 3.0)
        u_star = math.sqrt(tau / self.rho_w)
        return tau, u_star

    def calculate_dimensionless_transport(self, phi: float) -> float:
        if phi <= 0:
            return 0.0
        if phi < PHI_BREAK:
            return 0.002 * math.pow(phi, 7.5)
        return 14.0 * math.pow((1.0 - (0.894 / phi)), 4.5)

    def compute_daily_fractional_transport(self, q_flow: float):
        series = self.compute_transport_series(np.array([q_flow], dtype=float))
        return float(series[0])

    def compute_transport_series(self, q_flow) -> np.ndarray:
        if self._fi.size == 0:
            raise ValueError("Fractional parameters have not been loaded.")

        q = np.asarray(q_flow, dtype=float).reshape(-1)
        cross_section = self.bed_width * self.depth
        velocity = np.divide(q, cross_section, out=np.zeros_like(q), where=q > 0)
        tau = (self.rho_w * self.g * (self.manning_n ** 2) * (velocity ** 2)) / (self.depth ** (1.0 / 3.0))
        tau = np.where(q > 0, tau, 0.0)
        u_star = np.sqrt(tau / self.rho_w)

        phi = tau[:, None] / self._tau_ri[None, :]
        w_star = np.zeros_like(phi)
        low = (phi > 0) & (phi < PHI_BREAK)
        high = phi >= PHI_BREAK
        w_star = np.where(low, 0.002 * np.power(phi, 7.5), w_star)
        w_star = np.where(high, 14.0 * np.power(1.0 - (0.894 / np.where(high, phi, 1.0)), 4.5), w_star)

        # Calculates intermediate volumetric transport rate per unit width (m2/s)
        q_bi = (w_star * self._fi[None, :] * np.power(u_star[:, None], 3)) / ((self.s - 1.0) * self.g)
        total = q_bi.sum(axis=1)
        return np.where(tau == 0.0, 0.0, total)

    def _reference_stress_for_fraction(self, d_i: float) -> float:
        """Wilcock & Crowe tau_ri from sand fraction, D50, and grain size d_i."""
        tau_rm_star = 0.021 + 0.015 * math.exp(-20 * self.f_s)
        tau_rm = tau_rm_star * (self.s - 1) * self.rho_w * self.g * self.d50
        b = 0.67 / (1 + math.exp(1.5 - (d_i / self.d50)))
        return tau_rm * math.pow((d_i / self.d50), b)

    def load_fractional_parameters(self, df: pd.DataFrame):
        required = ["di", "Fi", "bi"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise KeyError(f"Fractional table missing columns: {missing}")

        cols = list(required)
        has_tau_ri = "tau_ri" in df.columns
        if has_tau_ri:
            cols.append("tau_ri")

        work = df[cols].apply(pd.to_numeric, errors="coerce")
        if work.isna().any().any():
            raise ValueError("Fractional parameters contain non-numeric or empty values.")

        if not has_tau_ri:
            work["tau_ri"] = [self._reference_stress_for_fraction(d_i) for d_i in work["di"]]

        if (work["tau_ri"] <= 0).any():
            raise ValueError("All tau_ri values must be greater than zero.")
        fi_sum = float(work["Fi"].sum())
        if not np.isclose(fi_sum, 1.0, atol=0.02):
            raise ValueError(f"Fi fractions must sum to ~1.0 (got {fi_sum:.4f}).")

        self.fractions = work.to_dict(orient="records")
        self._fi = work["Fi"].to_numpy(dtype=float)
        self._tau_ri = work["tau_ri"].to_numpy(dtype=float)


def year_column(columns) -> str:
    """Year key of a Wilcock table: Water_Year (DSI-derived, Oct-Sep) if present, else Year."""
    return WATER_YEAR_COLUMN if WATER_YEAR_COLUMN in columns else YEAR_COLUMN


class TimeSeriesAggregator:
    def __init__(self, model: FractionalModel):
        self.model = model
        self.warnings: List[str] = []

    def process_annual_averages(self, df_flow: pd.DataFrame) -> pd.DataFrame:
        """Annual summary indexed by Water_Year if the series carries that column, else by calendar Year."""
        if df_flow is None or df_flow.empty:
            raise ValueError("Flow table is empty.")

        self.warnings = []
        lookup = {normalize_header(col): col for col in df_flow.columns}
        water_year_col = lookup.get(normalize_header(WATER_YEAR_COLUMN))

        date_col = None
        for candidate in ["date", "tarih"]:
            if candidate in lookup:
                date_col = lookup[candidate]
                break

        flow_col = None
        for candidate in ["flow", "flowq(m3/s)", "debi"]:
            if candidate in lookup:
                flow_col = lookup[candidate]
                break

        if date_col is None or flow_col is None:
            raise KeyError(
                "Flow table must contain the columns: Date (or Tarih) and Flow Q (m3/s) "
                "(or the legacy Flow / Debi column). DSI monthly tables (Yıllar, Ekim...Eylül) must first be "
                "converted with prepare_daily_flow; the Wilcock tab does this automatically."
            )

        renames = {date_col: "Date", flow_col: "Flow Q (m3/s)"}
        if water_year_col is not None:
            renames[water_year_col] = WATER_YEAR_COLUMN
        df = df_flow.copy()
        df = df.rename(columns=renames)

        raw_dates = df["Date"]
        dates = pd.to_datetime(raw_dates, format="%d/%m/%Y", errors="coerce")
        retry = dates.isna() & raw_dates.notna()
        if retry.any():
            # Only reached for non-dd/mm/yyyy dates (e.g. ISO); unparseable values stay NaT.
            dates = dates.where(~retry, pd.to_datetime(raw_dates, format="mixed", dayfirst=True, errors="coerce"))
        df["Date"] = dates
        df["Flow Q (m3/s)"] = pd.to_numeric(df["Flow Q (m3/s)"], errors="coerce")

        required = ["Date", "Flow Q (m3/s)"]
        bad_water_years = 0
        if water_year_col is not None:
            water_years = pd.to_numeric(df[WATER_YEAR_COLUMN], errors="coerce")
            df[WATER_YEAR_COLUMN] = water_years.where(water_years % 1 == 0)
            bad_water_years = int(
                (df[WATER_YEAR_COLUMN].isna() & df["Date"].notna() & df["Flow Q (m3/s)"].notna()).sum()
            )
            required.append(WATER_YEAR_COLUMN)

        bad_dates = int(df["Date"].isna().sum())
        bad_flows = int((df["Flow Q (m3/s)"].isna() & df["Date"].notna()).sum())
        if bad_dates or bad_flows or bad_water_years:
            df = df.dropna(subset=required).reset_index(drop=True)
            message = (
                f"Dropped {bad_flows} row(s) with missing/non-numeric flow and "
                f"{bad_dates} row(s) with unparseable dates."
            )
            if bad_water_years:
                message += f" Dropped {bad_water_years} row(s) with a missing/non-integer {WATER_YEAR_COLUMN}."
            self.warnings.append(message)
        if df.empty:
            raise ValueError("Flow table has no rows with a valid date and flow value.")

        negative = df["Flow Q (m3/s)"] < 0
        if negative.any():
            first = ", ".join(df.loc[negative, "Date"].dt.strftime("%Y-%m-%d").head(5))
            raise ValueError(f"Flow values must not be negative (first offending dates: {first}).")

        # A DSI-derived series carries its own Water_Year (Oct (Y-1) to Sep (Y)); anything else is calendar.
        if water_year_col is not None:
            year_key = WATER_YEAR_COLUMN
            df[year_key] = df[year_key].astype(int)
        else:
            year_key = YEAR_COLUMN
            df[year_key] = df["Date"].dt.year

        # Calculate intermediate daily m2/s rate
        df["Daily_Bedload_Rate"] = self.model.compute_transport_series(df["Flow Q (m3/s)"].to_numpy(dtype=float))

        # Extract annual mean flow and mean transport rate
        annual_summary = df.groupby(year_key, as_index=True).agg(
            Annual_Average_Flow=("Flow Q (m3/s)", "mean"),
            Average_Rate_m2_s=("Daily_Bedload_Rate", "mean"),
        )

        annual_summary["Annual_Average_Bedload"] = annual_summary["Average_Rate_m2_s"]

        # Maintain the original volume-based result for compatibility with handoff/legacy reporting.
        annual_summary["Annual_Total_Bedload_m3_yr"] = (
            annual_summary["Average_Rate_m2_s"] * self.model.bed_width * SECONDS_PER_YEAR
        )

        # Convert the bedload volume to metric tons/year using sediment density.
        annual_summary["Annual_Average_Bed_Load_metric_tons_yr"] = (
            annual_summary["Annual_Total_Bedload_m3_yr"] * (self.model.rho_s / 1000.0)
        )

        return annual_summary

    def to_phase3_handoff(self, annual_summary: pd.DataFrame) -> pd.DataFrame:
        """Hand off the pre-calculated total annual volume."""
        if annual_summary.empty:
            raise ValueError("Annual summary is empty.")
        handoff = annual_summary.reset_index()
        handoff["Bedload_Volume_m3"] = handoff["Annual_Total_Bedload_m3_yr"]
        return handoff[[year_column(handoff.columns), "Bedload_Volume_m3"]]


class BedloadVisualizer:
    @staticmethod
    def prepare_summary_table(df_summary: pd.DataFrame) -> pd.DataFrame:
        if df_summary is None or df_summary.empty:
            raise ValueError("Dataframe is empty. Cannot generate summary table.")

        display = df_summary.reset_index().copy()
        year_key = year_column(display.columns)
        if year_key not in display.columns:
            display = display.rename(columns={display.columns[0]: YEAR_COLUMN})

        mass_col = "Annual_Average_Bed_Load_metric_tons_yr"
        if mass_col not in display.columns:
            if "Annual_Total_Bedload" in display.columns:
                display[mass_col] = display["Annual_Total_Bedload"] * 2.65
            elif "Annual_Total_Bedload_m3_yr" in display.columns:
                display[mass_col] = display["Annual_Total_Bedload_m3_yr"] * 2.65
            else:
                raise KeyError("Annual summary is missing bedload mass column.")

        required = [year_key, "Annual_Average_Flow", mass_col]
        missing = [col for col in required if col not in display.columns]
        if missing:
            raise KeyError(f"Annual summary is missing required columns: {missing}")

        table = display[required].copy()
        table = table.rename(
            columns={
                "Annual_Average_Flow": FLOW_COLUMN_LABEL,
                mass_col: BEDLOAD_COLUMN_LABEL,
            }
        )
        return table

    @staticmethod
    def export_summary_csv(df_summary: pd.DataFrame, save_path: str):
        table = BedloadVisualizer.prepare_summary_table(df_summary)
        table.to_csv(save_path, index=False, encoding="utf-8-sig")
        return table


    def generate_trend_graph(self, df_summary: pd.DataFrame):
        if df_summary.empty:
            raise ValueError("Dataframe is empty. Cannot generate plot.")

        fig, ax1 = plt.subplots(figsize=(10, 6))
        years = df_summary.index

        line1 = ax1.plot(years, df_summary["Annual_Average_Flow"], color="blue", marker="o", label="Average Flow")[0]
        year_label = "Water Year (Oct–Sep)" if df_summary.index.name == WATER_YEAR_COLUMN else "Year"
        ax1.set_xlabel(year_label, fontweight="bold")
        ax1.set_ylabel("Annual Average Flow (m³/s)", color="blue", fontweight="bold")
        ax1.tick_params(axis="y", labelcolor="blue")
        ax1.grid(True, linestyle="--", alpha=0.6)

        mass_col = "Annual_Average_Bed_Load_metric_tons_yr"
        if mass_col not in df_summary.columns:
            if "Annual_Total_Bedload" in df_summary.columns:
                bedload_series = df_summary["Annual_Total_Bedload"] * 2.65
            elif "Annual_Total_Bedload_m3_yr" in df_summary.columns:
                bedload_series = df_summary["Annual_Total_Bedload_m3_yr"] * 2.65
            else:
                raise KeyError("Annual summary is missing the bedload mass series for plotting.")
        else:
            bedload_series = df_summary[mass_col]

        ax2 = ax1.twinx()
        line2 = ax2.plot(
            years, bedload_series, color="red", marker="s", label="Bed Load"
        )[0]
        ax2.set_ylabel("Annual Average Bed Load (metric tons/year)", color="red", fontweight="bold")
        ax2.tick_params(axis="y", labelcolor="red")

        ax1.legend([line1, line2], [line1.get_label(), line2.get_label()], loc="upper left")
        ax1.set_title("Annual Flow vs. Bed Load Trends", fontweight="bold", pad=15)
        fig.tight_layout()

        return fig
