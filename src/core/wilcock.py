from dataclasses import dataclass
import math
from typing import List, Tuple

import numpy as np
import pandas as pd

from src.core.rusle import normalize_header

SECONDS_PER_YEAR = 365.25 * 24.0 * 3600.0
YEAR_COLUMN = "Year"
WATER_YEAR_COLUMN = "Water_Year"  # Oct (Y-1) to Sep (Y), carried by DSI-derived daily series
PHI_BREAK = 1.35
SUPPLIED_TOLERANCE = 0.01  # a supplied tau_ri or bi this far (relative) from the computed value is warned about


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
        self.warnings: List[str] = []  # cross-check findings of the last load_fractional_parameters
        self._fi = np.array([], dtype=float)
        self._tau_ri = np.array([], dtype=float)

    def calculate_hydraulics(self, q_flow: float) -> Tuple[float, float]:
        if q_flow <= 0:
            return 0.0, 0.0
        area = self.bed_width * self.depth
        velocity = q_flow / area
        tau = (self.rho_w * self.g * (self.manning_n**2) * (velocity**2)) / math.pow(self.depth, 1.0 / 3.0)
        u_star = math.sqrt(tau / self.rho_w)
        return tau, u_star

    def calculate_dimensionless_transport(self, phi: float) -> float:
        if phi <= 0:
            return 0.0
        if phi < PHI_BREAK:
            return 0.002 * math.pow(phi, 7.5)
        return 14.0 * math.pow((1.0 - (0.894 / math.sqrt(phi))), 4.5)

    def compute_daily_fractional_transport(self, q_flow: float):
        series = self.compute_transport_series(np.array([q_flow], dtype=float))
        return float(series[0])

    def compute_transport_series(self, q_flow) -> np.ndarray:
        if self._fi.size == 0:
            raise ValueError("Fractional parameters have not been loaded.")

        q = np.asarray(q_flow, dtype=float).reshape(-1)
        cross_section = self.bed_width * self.depth
        velocity = np.divide(q, cross_section, out=np.zeros_like(q), where=q > 0)
        tau = (self.rho_w * self.g * (self.manning_n**2) * (velocity**2)) / (self.depth ** (1.0 / 3.0))
        tau = np.where(q > 0, tau, 0.0)
        u_star = np.sqrt(tau / self.rho_w)

        phi = tau[:, None] / self._tau_ri[None, :]
        w_star = np.zeros_like(phi)
        low = (phi > 0) & (phi < PHI_BREAK)
        high = phi >= PHI_BREAK
        w_star = np.where(low, 0.002 * np.power(phi, 7.5), w_star)
        w_star = np.where(high, 14.0 * np.power(1.0 - (0.894 / np.sqrt(np.where(high, phi, 1.0))), 4.5), w_star)

        # Calculates intermediate volumetric transport rate per unit width (m2/s)
        q_bi = (w_star * self._fi[None, :] * np.power(u_star[:, None], 3)) / ((self.s - 1.0) * self.g)
        total = q_bi.sum(axis=1)
        return np.where(tau == 0.0, 0.0, total)

    def _exponent_for_fraction(self, d_i: float) -> float:
        """Wilcock & Crowe exponent b_i for grain size d_i."""
        return 0.67 / (1 + math.exp(1.5 - (d_i / self.d50)))

    def _reference_stress_for_fraction(self, d_i: float) -> float:
        """Wilcock & Crowe tau_ri from sand fraction, D50, and grain size d_i."""
        tau_rm_star = 0.021 + 0.015 * math.exp(-20 * self.f_s)
        tau_rm = tau_rm_star * (self.s - 1) * self.rho_w * self.g * self.d50
        return tau_rm * math.pow((d_i / self.d50), self._exponent_for_fraction(d_i))

    def load_fractional_parameters(self, df: pd.DataFrame):
        """Load the grain fractions. di and Fi are required. tau_ri and bi are always computed (D36); a supplied
        column is only cross-checked, and a value more than 1% from the computed one adds a warning."""
        missing = [col for col in ("di", "Fi") if col not in df.columns]
        if missing:
            raise KeyError(f"Fractional table missing columns: {missing}")

        work = df[["di", "Fi"]].apply(pd.to_numeric, errors="coerce")
        if work.isna().any().any():
            raise ValueError("Fractional parameters contain non-numeric or empty values.")
        if (work["di"] <= 0).any():
            raise ValueError("All di values (grain diameters in m) must be greater than zero.")
        if (work["Fi"] < 0).any():
            raise ValueError("All Fi fractions must be zero or greater.")
        fi_sum = float(work["Fi"].sum())
        if not np.isclose(fi_sum, 1.0, atol=0.02):
            raise ValueError(f"Fi fractions must sum to ~1.0 (got {fi_sum:.4f}).")

        work["bi"] = [self._exponent_for_fraction(d_i) for d_i in work["di"]]
        work["tau_ri"] = [self._reference_stress_for_fraction(d_i) for d_i in work["di"]]

        self.warnings = []
        for name in ("bi", "tau_ri"):
            if name not in df.columns:
                continue
            supplied = pd.to_numeric(df[name], errors="coerce")
            for position, (d_i, given, computed) in enumerate(zip(work["di"], supplied, work[name]), start=1):
                if pd.notna(given) and abs(given - computed) > SUPPLIED_TOLERANCE * computed:
                    self.warnings.append(
                        f"Fraction {position} (di = {d_i * 1000:g} mm): the supplied {name} {given:g} differs from "
                        f"the computed {computed:.4g} by {abs(given - computed) / computed:.1%}; the computed value is used."
                    )

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
                "Flow table must contain the columns: Date (or Tarih) and Flow (or Flow Q (m3/s), Debi), "
                "or be a DSI monthly table with the columns Yıllar and Ekim...Eylül."
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
        annual_summary["Annual_Average_Bed_Load_metric_tons_yr"] = annual_summary["Annual_Total_Bedload_m3_yr"] * (
            self.model.rho_s / 1000.0
        )

        return annual_summary

    def to_phase3_handoff(self, annual_summary: pd.DataFrame) -> pd.DataFrame:
        """Hand off the pre-calculated total annual volume."""
        if annual_summary.empty:
            raise ValueError("Annual summary is empty.")
        handoff = annual_summary.reset_index()
        handoff["Bedload_Volume_m3"] = handoff["Annual_Total_Bedload_m3_yr"]
        return handoff[[year_column(handoff.columns), "Bedload_Volume_m3"]]
