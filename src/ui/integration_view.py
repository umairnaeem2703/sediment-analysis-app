from pathlib import Path
import tkinter as tk
from tkinter import ttk

import numpy as np
import pandas as pd

from src.core.wilcock import WATER_YEAR_COLUMN, year_column
from src.data.reporter import IntegrationModule
from src.ui.common import (
    browse_open_file,
    browse_save_file,
    show_error,
    show_info,
    show_warning,
)
from src.utils.paths import read_table, resource_path


class IntegrationView:
    def __init__(self, parent_notebook: ttk.Notebook, app_controller):
        self.notebook = parent_notebook
        self.app = app_controller
        self.frame = ttk.Frame(self.notebook)
        self.notebook.add(self.frame, text="Integration & Handoff")

        self.phase2_file_var = tk.StringVar()
        self.phase3_file_var = tk.StringVar()
        self.bathy_file_var = tk.StringVar()

        self._setup_ui()

    def _setup_ui(self):
        self.frame.columnconfigure(0, weight=0)
        self.frame.columnconfigure(1, weight=1)

        ttk.Button(
            self.frame,
            text="Browse Phase 2 Output (CSV)",
            command=lambda: self.browse_file(self.phase2_file_var),
        ).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        ttk.Entry(self.frame, textvariable=self.phase2_file_var, width=50, state="readonly").grid(
            row=0, column=1, padx=10, pady=5, sticky="ew"
        )

        ttk.Button(
            self.frame,
            text="Browse Phase 3 Output (CSV)",
            command=lambda: self.browse_file(self.phase3_file_var),
        ).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        ttk.Entry(self.frame, textvariable=self.phase3_file_var, width=50, state="readonly").grid(
            row=1, column=1, padx=10, pady=5, sticky="ew"
        )

        ttk.Button(
            self.frame,
            text="Browse Bathymetry (Optional)",
            command=lambda: self.browse_file(self.bathy_file_var),
        ).grid(row=2, column=0, padx=10, pady=5, sticky="w")
        ttk.Entry(self.frame, textvariable=self.bathy_file_var, width=50, state="readonly").grid(
            row=2, column=1, padx=10, pady=5, sticky="ew"
        )

        self.btn_run_integration = ttk.Button(
            self.frame, text="Merge Data & Find Extremes", command=self.execute_integration
        )
        self.btn_run_integration.grid(row=3, column=0, columnspan=2, pady=10)

        self.results_text = tk.Text(self.frame, height=14, width=70, state="disabled")
        self.results_text.grid(row=4, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")
        self.frame.rowconfigure(4, weight=1)

        self.btn_export_master = ttk.Button(
            self.frame,
            text="Export Master Dataset",
            command=self.export_master_dataset,
            state="disabled",
        )
        self.btn_export_master.grid(row=5, column=0, columnspan=2, pady=10)

    def browse_file(self, string_var):
        filepath = browse_open_file(title="Select Dataset File")
        if filepath:
            string_var.set(filepath)

    def _ensure_phase2_volume(self, df_p2: pd.DataFrame) -> pd.DataFrame:
        self._zonal_notes = []
        if "Suspended_Volume_m3" in df_p2.columns or "Volume_m3_yr" in df_p2.columns:
            return df_p2
        if "volume_m3" in df_p2.columns:
            return df_p2.rename(columns={"volume_m3": "Suspended_Volume_m3"})

        from src.core.rusle import YieldCalculator, ZonalMatcher, find_basin_table_columns

        col_map = find_basin_table_columns(df_p2.columns)
        area_col, slope_col, subbasin_col = col_map.get("area"), col_map.get("slope"), col_map.get("subbasin")
        if not (area_col and slope_col):
            return df_p2

        zonal_path = self.app.zonal_file_var.get().strip()
        if not zonal_path:
            raise ValueError(
                "Phase 2 table has no volume column. Choose a Zonal Statistics CSV on the RUSLE tab, "
                "or run the RUSLE analysis first."
            )
        if not subbasin_col:
            raise ValueError("Phase 2 table needs a Sub-basin column to match against the zonal statistics file.")

        lookup = ZonalMatcher.build_lookup(read_table(zonal_path))
        resolution = ZonalMatcher.resolve_all(lookup, df_p2[subbasin_col])
        if resolution.unresolved:
            raise ZonalMatcher.unresolved_error(lookup, resolution.unresolved)
        self._zonal_notes = [f"{name} matched approximately to zonal '{key}'" for name, key in sorted(resolution.loose.items())]

        calc = YieldCalculator()
        total_vol = sum(
            calc.calculate_metrics(mean_val, float(area), float(slope))["volume_m3"]
            for mean_val, area, slope in zip(resolution.means, df_p2[area_col], df_p2[slope_col])
        )
        return pd.DataFrame({"Suspended_Volume_m3": [total_vol]})

    def _load_default_phase3(self) -> pd.DataFrame:
        from src.core.wilcock import FractionalModel, TimeSeriesAggregator

        flow_path = resource_path("inputs", "daily_flow_data.csv")
        frac_path = resource_path("inputs", "fractional_parameters.csv")
        if Path(flow_path).exists() and Path(frac_path).exists():
            df_flow = read_table(flow_path)
            df_frac = read_table(frac_path)
            model = FractionalModel()
            model.load_fractional_parameters(df_frac)
            agg = TimeSeriesAggregator(model)
            summary = agg.process_annual_averages(df_flow)
            return agg.to_phase3_handoff(summary)
        return None

    # Sentinel: pass df_bathy=IntegrationView._NO_BATHY to explicitly disable auto-loading
    _NO_BATHY = object()

    def execute_integration(self, df_p2: pd.DataFrame = None, df_p3: pd.DataFrame = None, df_bathy=None):
        p2_path = self.phase2_file_var.get().strip()
        p3_path = self.phase3_file_var.get().strip()
        bathy_path = self.bathy_file_var.get().strip()

        try:
            # 1. Ingest df_p2: browsed file, or app handoff, or inputs/master_yield.csv
            if df_p2 is None:
                if p2_path:
                    df_p2 = read_table(p2_path)
                elif getattr(self.app, "phase2_df", None) is not None and not self.app.phase2_df.empty:
                    df_p2 = self.app.phase2_df
                elif getattr(self.app, "rusle_results_df", None) is not None and not self.app.rusle_results_df.empty:
                    df_p2 = self.app.rusle_results_df
                elif Path(resource_path("inputs", "master_yield.csv")).exists():
                    df_p2 = read_table(resource_path("inputs", "master_yield.csv"))
                elif Path("inputs/master_yield.csv").exists():
                    df_p2 = read_table("inputs/master_yield.csv")

            if df_p2 is None or df_p2.empty:
                show_error("Input Error", "Phase 2 dataset is required. Browse a file or run RUSLE analysis first.")
                return

            df_p2 = self._ensure_phase2_volume(df_p2)

            # Ingest df_p3: browsed file, or app handoff, or default daily flow data
            if df_p3 is None:
                if p3_path:
                    df_p3 = read_table(p3_path)
                elif getattr(self.app, "phase3_df", None) is not None and not self.app.phase3_df.empty:
                    df_p3 = self.app.phase3_df
                elif Path(resource_path("inputs", "daily_flow_data.csv")).exists() or Path("inputs/daily_flow_data.csv").exists():
                    df_p3 = self._load_default_phase3()

            if df_p3 is None or df_p3.empty:
                show_error("Input Error", "Phase 3 dataset is required. Browse a file or run Wilcock analysis first.")
                return

            # Ingest df_bathy: None means auto-load; _NO_BATHY means explicitly disabled
            if df_bathy is None:
                if bathy_path:
                    df_bathy = read_table(bathy_path)
                elif Path(resource_path("inputs", "bathymetry.csv")).exists():
                    df_bathy = read_table(resource_path("inputs", "bathymetry.csv"))
                elif Path("inputs/bathymetry.csv").exists():
                    df_bathy = read_table("inputs/bathymetry.csv")
            elif df_bathy is IntegrationView._NO_BATHY:
                df_bathy = None

            integration = IntegrationModule()
            merged_df, join_warning = integration.merge_sediment_data(df_p2, df_p3)

            interp_warnings = []
            if df_bathy is not None and not df_bathy.empty:
                elevations, interp_warnings = integration.interpolate_elevation(
                    df_bathy,
                    merged_df["Total_Volume_m3"].tolist(),
                    return_warnings=True,
                )
                merged_df["Interpolated_Elevation_m"] = elevations
                merged_df["Elevation_m"] = elevations
                merged_df["Elevation"] = elevations
            else:
                merged_df["Interpolated_Elevation_m"] = float("nan")
                merged_df["Elevation_m"] = float("nan")
                merged_df["Elevation"] = float("nan")

            self.app.set_integration_results(merged_df)
            min_record, max_record = integration.locate_extremes(merged_df)

            if "Interpolated_Elevation_m" in merged_df.columns:
                min_idx = merged_df["Total_Volume_m3"].idxmin()
                max_idx = merged_df["Total_Volume_m3"].idxmax()
                min_record["Interpolated_Elevation_m"] = merged_df.loc[min_idx, "Interpolated_Elevation_m"]
                max_record["Interpolated_Elevation_m"] = merged_df.loc[max_idx, "Interpolated_Elevation_m"]

            # Bedload from a DSI monthly run is keyed by Water_Year (Oct-Sep); cast to int for clean display
            year_key = year_column(merged_df.columns)
            year_label = "Water Year" if year_key == WATER_YEAR_COLUMN else "Year"
            min_year = int(min_record[year_key])
            max_year = int(max_record[year_key])

            self.results_text.config(state="normal")
            self.results_text.delete(1.0, tk.END)

            report = (
                "==================================================\n"
                "       SEDIMENT INTEGRATION SUMMARY REPORT        \n"
                "==================================================\n\n"
                "Minimum Sediment Year (Best Case):\n"
                f"  {year_label}: {min_year}\n"
                f"  Total Volume: {min_record['Total_Volume_m3']:,.2f} m³\n"
            )
            if "Interpolated_Elevation_m" in min_record and pd.notna(min_record["Interpolated_Elevation_m"]):
                report += f"  Interpolated Water Elevation: {min_record['Interpolated_Elevation_m']:.2f} m\n"
            else:
                report += "  Interpolated Water Elevation: N/A\n"

            report += (
                "\nMaximum Sediment Year (Worst Case):\n"
                f"  {year_label}: {max_year}\n"
                f"  Total Volume: {max_record['Total_Volume_m3']:,.2f} m³\n"
            )
            if "Interpolated_Elevation_m" in max_record and pd.notna(max_record["Interpolated_Elevation_m"]):
                report += f"  Interpolated Water Elevation: {max_record['Interpolated_Elevation_m']:.2f} m\n"
            else:
                report += "  Interpolated Water Elevation: N/A\n"

            if join_warning:
                report += f"\nNote: {join_warning}\n"
            for warning in interp_warnings:
                report += f"\n{warning}\n"

            self.results_text.insert(tk.END, report)
            self.results_text.config(state="disabled")
            self.btn_export_master.config(state="normal")
            notes = list(filter(None, [join_warning] + interp_warnings)) + getattr(self, "_zonal_notes", [])
            if notes:
                show_warning("Integration Notes", "\n".join(notes))
        except Exception as exc:
            show_error("Integration Error", f"Failed to merge datasets:\n\n{exc}")

    def export_master_dataset(self, save_path: str = None):
        if self.app.final_merged_df is None or self.app.final_merged_df.empty:
            show_error("Export Error", "No integrated dataset available to export. Run integration first.")
            return None

        if not save_path:
            save_path = browse_save_file(
                title="Save Master Dataset",
                defaultextension=".xlsx",
                filetypes=[
                    ("Excel Files", "*.xlsx"),
                    ("CSV Files", "*.csv"),
                    ("All Files", "*.*"),
                ],
            )

        if save_path:
            try:
                if save_path.lower().endswith(".csv"):
                    self.app.final_merged_df.to_csv(save_path, index=False, encoding="utf-8-sig")
                else:
                    self.app.final_merged_df.to_excel(save_path, index=False)
                show_info("Success", f"Master Dataset saved to:\n{save_path}")
                return save_path
            except Exception as exc:
                show_error("Export Error", f"Failed to save file:\n\n{exc}")
                return None
        return None
