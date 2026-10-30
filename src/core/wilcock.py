"""Wilcock & Crowe fractional bedload (B3.2). `FractionalModel` computes the shear stress from daily flow (Manning,
rectangular channel) and the transport of each grain-size fraction, vectorised in `compute_transport_series`. `tau_ri`
and `bi` are always computed from the grain size; a supplied column is only cross-checked into
`FractionalModel.warnings` (D36). `check_daily_flow` holds the structural checks of a daily flow series, and
`TimeSeriesAggregator` turns it into annual summaries.
"""

import math
from typing import List, Tuple

import numpy as np
import pandas as pd

SECONDS_PER_YEAR = 365.25 * 24.0 * 3600.0
YEAR_COLUMN = "Year"
DATE_COLUMN = "Date"
FLOW_COLUMN = "Flow Q (m3/s)"
WATER_YEAR_COLUMN = "Water_Year"  # Oct (Y-1) to Sep (Y), carried by DSI-derived daily series
PHI_BREAK = 1.35
SUPPLIED_TOLERANCE = 0.01  # a supplied tau_ri or bi this far (relative) from the computed value is warned about


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

    def calculate_hydraulics(self, q_flow):
        """Shear stress (Pa) and shear velocity (m/s) of a discharge, or of each discharge in an array; no flow gives
        zero. One code path serves a single value and the series."""
        q = np.asarray(q_flow, dtype=float)
        velocity = np.where(q > 0, q / (self.bed_width * self.depth), 0.0)
        tau = (self.rho_w * self.g * (self.manning_n**2) * (velocity**2)) / (self.depth ** (1.0 / 3.0))
        u_star = np.sqrt(tau / self.rho_w)
        return (float(tau), float(u_star)) if q.ndim == 0 else (tau, u_star)

    def calculate_dimensionless_transport(self, phi):
        """W* of a stress ratio, or of each ratio in an array (D35); a ratio of 0 or less gives zero."""
        phi = np.asarray(phi, dtype=float)
        low = (phi > 0) & (phi < PHI_BREAK)
        high = phi >= PHI_BREAK
        w_star = np.zeros_like(phi)
        w_star = np.where(low, 0.002 * np.power(np.where(low, phi, 1.0), 7.5), w_star)
        w_star = np.where(high, 14.0 * np.power(1.0 - (0.894 / np.sqrt(np.where(high, phi, 1.0))), 4.5), w_star)
        return float(w_star) if phi.ndim == 0 else w_star

    def compute_transport_series(self, q_flow) -> np.ndarray:
        if self._fi.size == 0:
            raise ValueError("Fractional parameters have not been loaded.")

        q = np.asarray(q_flow, dtype=float).reshape(-1)
        tau, u_star = self.calculate_hydraulics(q)
        w_star = self.calculate_dimensionless_transport(tau[:, None] / self._tau_ri[None, :])

        # Calculates intermediate volumetric transport rate per unit width (m2/s)
        q_bi = (w_star * self._fi[None, :] * np.power(u_star[:, None], 3)) / ((self.s - 1.0) * self.g)
        total = q_bi.sum(axis=1)
        return np.where(tau == 0.0, 0.0, total)

    def _exponent_for_fraction(self, d_i: float) -> float:
        """Wilcock & Crowe exponent b_i for grain size d_i."""
        return 0.67 / (1 + math.exp(1.5 - (d_i / self.d50)))

    def _reference_stress_for_fraction(self, d_i: float) -> float:
        """tau_ri (Pa) as the hydrologist computes it (D50): the hiding function scales the Shields number,
        tau_ri* = tau_rm* (d_i / D50)^b_i, which is then converted to a stress with the fraction's own d_i."""
        tau_rm_star = 0.021 + 0.015 * math.exp(-20 * self.f_s)
        tau_ri_star = tau_rm_star * math.pow((d_i / self.d50), self._exponent_for_fraction(d_i))
        return tau_ri_star * (self.s - 1) * self.rho_w * self.g * d_i

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
            for position, (d_i, given, computed) in enumerate(
                zip(work["di"], supplied, work[name], strict=True), start=1
            ):
                if pd.notna(given) and abs(given - computed) > SUPPLIED_TOLERANCE * computed:
                    self.warnings.append(
                        f"Fraction {position} (di = {d_i * 1000:g} mm): the supplied {name} {given:g} differs from "
                        f"the computed {computed:.4g} by {abs(given - computed) / computed:.1%}; the computed value is used."
                    )

        self.fractions = work.to_dict(orient="records")
        self._fi = work["Fi"].to_numpy(dtype=float)
        self._tau_ri = work["tau_ri"].to_numpy(dtype=float)


def check_daily_flow(df_flow: pd.DataFrame) -> Tuple[pd.DataFrame, str, List[str]]:
    """Check a daily flow table and prepare it for the annual summary: the table with valid rows only and its year
    column, the name of that column (Water_Year if the series carries it, else Year) and the warnings. Raises
    KeyError for a missing column and ValueError for an empty series, a negative or infinite flow or a date listed twice.
    No model
    is needed, so a file can be checked as it is chosen."""
    if df_flow is None or df_flow.empty:
        raise ValueError("Flow table is empty.")

    warnings: List[str] = []
    if DATE_COLUMN not in df_flow.columns or FLOW_COLUMN not in df_flow.columns:
        raise KeyError(f"Flow table must contain the columns '{DATE_COLUMN}' and '{FLOW_COLUMN}'.")
    water_year_col = WATER_YEAR_COLUMN if WATER_YEAR_COLUMN in df_flow.columns else None
    df = df_flow.copy()

    raw_dates = df[DATE_COLUMN]
    dates = pd.to_datetime(raw_dates, format="%d/%m/%Y", errors="coerce")
    retry = dates.isna() & raw_dates.notna()
    if retry.any():
        # Only reached for non-dd/mm/yyyy dates (e.g. ISO); unparseable values stay NaT.
        dates = dates.where(~retry, pd.to_datetime(raw_dates, format="mixed", dayfirst=True, errors="coerce"))
    df[DATE_COLUMN] = dates
    df[FLOW_COLUMN] = pd.to_numeric(df[FLOW_COLUMN], errors="coerce")

    required = [DATE_COLUMN, FLOW_COLUMN]
    bad_water_years = 0
    if water_year_col is not None:
        water_years = pd.to_numeric(df[WATER_YEAR_COLUMN], errors="coerce")
        df[WATER_YEAR_COLUMN] = water_years.where(water_years % 1 == 0)
        bad_water_years = int((df[WATER_YEAR_COLUMN].isna() & df[DATE_COLUMN].notna() & df[FLOW_COLUMN].notna()).sum())
        required.append(WATER_YEAR_COLUMN)

    bad_dates = int(df[DATE_COLUMN].isna().sum())
    bad_flows = int((df[FLOW_COLUMN].isna() & df[DATE_COLUMN].notna()).sum())
    if bad_dates or bad_flows or bad_water_years:
        df = df.dropna(subset=required).reset_index(drop=True)
        message = (
            f"Dropped {bad_flows} row(s) with missing/non-numeric flow and {bad_dates} row(s) with unparseable dates."
        )
        if bad_water_years:
            message += f" Dropped {bad_water_years} row(s) with a missing/non-integer {WATER_YEAR_COLUMN}."
        warnings.append(message)
    if df.empty:
        raise ValueError("Flow table has no rows with a valid date and flow value.")

    infinite = ~np.isfinite(df[FLOW_COLUMN])
    if infinite.any():
        first = ", ".join(df.loc[infinite, DATE_COLUMN].dt.strftime("%Y-%m-%d").head(5))
        raise ValueError(f"Flow values must be finite numbers (first offending dates: {first}).")

    negative = df[FLOW_COLUMN] < 0
    if negative.any():
        first = ", ".join(df.loc[negative, DATE_COLUMN].dt.strftime("%Y-%m-%d").head(5))
        raise ValueError(f"Flow values must not be negative (first offending dates: {first}).")

    repeated = df[DATE_COLUMN].duplicated()
    if repeated.any():
        first = ", ".join(df.loc[repeated, DATE_COLUMN].dt.strftime("%Y-%m-%d").head(5))
        raise ValueError(f"Each date may appear only once (first repeated dates: {first}).")
    missing_days = (df[DATE_COLUMN].max() - df[DATE_COLUMN].min()).days + 1 - len(df)
    if missing_days > 0:
        warnings.append(
            f"{missing_days} day(s) between the first and last date have no flow; the annual means use the days present."
        )

    # A DSI-derived series carries its own Water_Year (Oct (Y-1) to Sep (Y)); anything else is calendar.
    if water_year_col is not None:
        year_key = WATER_YEAR_COLUMN
        df[year_key] = df[year_key].astype(int)
    else:
        year_key = YEAR_COLUMN
        df[year_key] = df[DATE_COLUMN].dt.year

    return df, year_key, warnings


class TimeSeriesAggregator:
    def __init__(self, model: FractionalModel):
        self.model = model
        self.warnings: List[str] = []

    def process_annual_averages(self, df_flow: pd.DataFrame) -> pd.DataFrame:
        """Annual summary indexed by Water_Year if the series carries that column, else by calendar Year."""
        self.warnings = []  # a check that raises leaves none of an earlier run behind
        df, year_key, self.warnings = check_daily_flow(df_flow)

        # Calculate intermediate daily m2/s rate
        df["Daily_Bedload_Rate"] = self.model.compute_transport_series(df["Flow Q (m3/s)"].to_numpy(dtype=float))

        # Extract annual mean flow and mean transport rate
        annual_summary = df.groupby(year_key, as_index=True).agg(
            Annual_Average_Flow=("Flow Q (m3/s)", "mean"),
            Average_Rate_m2_s=("Daily_Bedload_Rate", "mean"),
        )

        # The annual volume in m3 (mean rate times the channel width times the seconds in a year).
        annual_summary["Annual_Total_Bedload_m3_yr"] = (
            annual_summary["Average_Rate_m2_s"] * self.model.bed_width * SECONDS_PER_YEAR
        )

        # Convert the bedload volume to metric tons/year using sediment density.
        annual_summary["Annual_Average_Bed_Load_metric_tons_yr"] = annual_summary["Annual_Total_Bedload_m3_yr"] * (
            self.model.rho_s / 1000.0
        )

        return annual_summary
