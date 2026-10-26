"""Bedload tables and charts (FR-M3-05). Moved out of `src/core`, which must hold no plotting (B2)."""

import matplotlib.pyplot as plt
import pandas as pd

from src.core.wilcock import WATER_YEAR_COLUMN, YEAR_COLUMN, year_column

FLOW_COLUMN_LABEL = "Annual Average Flow (m3/s)"
BEDLOAD_COLUMN_LABEL = "Annual Average Bed Load (metric tons/year)"


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
        line2 = ax2.plot(years, bedload_series, color="red", marker="s", label="Bed Load")[0]
        ax2.set_ylabel("Annual Average Bed Load (metric tons/year)", color="red", fontweight="bold")
        ax2.tick_params(axis="y", labelcolor="red")

        ax1.legend([line1, line2], [line1.get_label(), line2.get_label()], loc="upper left")
        ax1.set_title("Annual Flow vs. Bed Load Trends", fontweight="bold", pad=15)
        fig.tight_layout()

        return fig
