import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

SECONDS_PER_YEAR = 365.25 * 24.0 * 3600.0
PHI_BREAK = 1.35


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

    def calculate_hydraulics(self, q_flow: float):
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


class TimeSeriesAggregator:
    def __init__(self, model: FractionalModel):
        self.model = model

    def process_annual_averages(self, df_flow: pd.DataFrame) -> pd.DataFrame:
        if df_flow is None or df_flow.empty:
            raise ValueError("Flow table is empty.")

        normalized = {str(col).strip(): col for col in df_flow.columns}
        lookup = {str(col).strip().lower(): col for col in df_flow.columns}

        date_col = None
        for candidate in ["date"]:
            if candidate in lookup:
                date_col = lookup[candidate]
                break

        flow_candidates = ["flow q (m3/s)", "flow", "flow q (m^3/s)"]
        flow_col = None
        for candidate in flow_candidates:
            if candidate in lookup:
                flow_col = lookup[candidate]
                break

        if date_col is None or flow_col is None:
            raise KeyError(
                "Flow table must contain the columns: Date and Flow Q (m3/s) "
                "(or the legacy Flow column)."
            )

        df = df_flow.copy()
        df = df.rename(columns={date_col: "Date", flow_col: "Flow Q (m3/s)"})
        try:
            df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y")
        except (ValueError, TypeError):
            df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)
            
        df["Year"] = df["Date"].dt.year
        
        # Calculate intermediate daily m2/s rate
        df["Daily_Bedload_Rate"] = self.model.compute_transport_series(df["Flow Q (m3/s)"].to_numpy(dtype=float))

        # Extract annual mean flow and mean transport rate
        annual_summary = df.groupby("Year", as_index=True).agg(
            Annual_Average_Flow=("Flow Q (m3/s)", "mean"),
            Average_Rate_m2_s=("Daily_Bedload_Rate", "mean"),
        )

        annual_summary["Annual_Average_Bedload"] = annual_summary["Average_Rate_m2_s"]

        # Extrapolate gap-safe mean to true total annual volume
        annual_summary["Annual_Total_Bedload"] = (
            annual_summary["Average_Rate_m2_s"] * self.model.bed_width * SECONDS_PER_YEAR
        )

        return annual_summary

    def to_phase3_handoff(self, annual_summary: pd.DataFrame) -> pd.DataFrame:
        """Hand off the pre-calculated total annual volume."""
        if annual_summary.empty:
            raise ValueError("Annual summary is empty.")
        handoff = annual_summary.reset_index()
        handoff["Bedload_Volume_m3"] = handoff["Annual_Total_Bedload"]
        return handoff[["Year", "Bedload_Volume_m3"]]


class BedloadVisualizer:
    @staticmethod
    def prepare_summary_table(df_summary: pd.DataFrame) -> pd.DataFrame:
        if df_summary is None or df_summary.empty:
            raise ValueError("Dataframe is empty. Cannot generate summary table.")

        display = df_summary.reset_index().copy()
        if "Year" not in display.columns:
            display = display.rename(columns={display.columns[0]: "Year"})
            
        required = ["Year", "Annual_Average_Flow", "Annual_Total_Bedload"]
        missing = [col for col in required if col not in display.columns]
        if missing:
            raise KeyError(f"Annual summary is missing required columns: {missing}")

        table = display[["Year", "Annual_Average_Flow", "Annual_Total_Bedload"]].copy()
        table = table.rename(
            columns={
                "Year": "Year",
                "Annual_Average_Flow": "Annual Average Flow (m3/s)",
                "Annual_Total_Bedload": "Annual Total Bedload (m3/year)",
            }
        )
        return table

    @staticmethod
    def export_summary_csv(df_summary: pd.DataFrame, save_path: str):
        table = BedloadVisualizer.prepare_summary_table(df_summary)
        table.to_csv(save_path, index=False)
        return table

    def generate_trend_graph(self, df_summary: pd.DataFrame):
        if df_summary.empty:
            raise ValueError("Dataframe is empty. Cannot generate plot.")
            
        fig, ax1 = plt.subplots(figsize=(10, 6))
        years = df_summary.index
        
        line1 = ax1.plot(years, df_summary["Annual_Average_Flow"], color="blue", marker="o", label="Average Flow")[0]
        ax1.set_xlabel("Year", fontweight="bold")
        ax1.set_ylabel("Annual Average Flow (m³/s)", color="blue", fontweight="bold")
        ax1.tick_params(axis="y", labelcolor="blue")
        ax1.grid(True, linestyle="--", alpha=0.6)

        ax2 = ax1.twinx()
        line2 = ax2.plot(
            years, df_summary["Annual_Total_Bedload"], color="red", marker="s", label="Total Bedload"
        )[0]
        ax2.set_ylabel("Annual Total Bedload (m³/year)", color="red", fontweight="bold")
        ax2.tick_params(axis="y", labelcolor="red")
        
        ax1.legend([line1, line2], [line1.get_label(), line2.get_label()], loc="upper left")
        ax1.set_title("Annual Flow vs. Bedload Transport Trends", fontweight="bold", pad=15)
        fig.tight_layout()
        
        return fig