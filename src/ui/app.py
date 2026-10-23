from pathlib import Path
import tkinter as tk
from tkinter import ttk

from src.core.rusle import YieldCalculator
from src.ui.integration_view import IntegrationView
from src.ui.rusle_view import RusleView
from src.ui.wilcock_view import WilcockView


class SedimentApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Automated Sediment Analysis Software")
        self.root.geometry("980x720")

        self.yield_calc = YieldCalculator()
        self.rusle_metrics = None
        self.rusle_row_metrics = None
        self.rusle_results_df = None
        self.phase2_df = None
        self.phase3_df = None
        self.annual_summary = None
        self.final_merged_df = None

        self.load_startup_data()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=10)

        # Tab views
        self.rusle_view = RusleView(self.notebook, self)
        self.wc_view = WilcockView(self.notebook, self)
        self.integration_view = IntegrationView(self.notebook, self)

    def load_startup_data(self):
        self.default_basin_path = ""
        self.default_raster_path = ""
        self.default_zonal_path = ""

    def set_rusle_results(self, row_metrics: list, results_df, phase2_df):
        """Set calculation results from the RUSLE Spatial Engine."""
        self.rusle_row_metrics = row_metrics
        self.rusle_results_df = results_df
        self.rusle_metrics = row_metrics[0] if row_metrics else None
        self.phase2_df = phase2_df

    def set_wilcock_results(self, annual_summary, phase3_df):
        """Set calculation results from the Wilcock & Crowe bedload model."""
        self.annual_summary = annual_summary
        self.phase3_df = phase3_df

    def set_integration_results(self, merged_df):
        """Set merged results from the Integration module."""
        self.final_merged_df = merged_df

    # Backwards-compatible aliases for views/tests
    @property
    def rusle_frame(self):
        return self.rusle_view.frame

    @property
    def basin_tree(self):
        return self.rusle_view.basin_tree

    @property
    def results_tree(self):
        return self.rusle_view.results_tree

    @property
    def basin_file_var(self):
        return self.rusle_view.basin_file_var

    @property
    def zonal_file_var(self):
        return self.rusle_view.zonal_file_var

    @property
    def btn_export_phase2(self):
        return self.rusle_view.btn_export_phase2

    @property
    def wc_frame(self):
        return self.wc_view.frame

    @property
    def flow_file_var(self):
        return self.wc_view.flow_file_var

    @property
    def frac_file_var(self):
        return self.wc_view.frac_file_var

    @property
    def btn_export_png(self):
        return self.wc_view.btn_export_png

    @property
    def btn_show_summary(self):
        return self.wc_view.btn_show_summary

    @property
    def btn_export_summary(self):
        return self.wc_view.btn_export_summary

    @property
    def btn_export_phase3(self):
        return self.wc_view.btn_export_phase3

    @property
    def wc_status_var(self):
        return self.wc_view.wc_status_var

    @property
    def wc_graph_frame(self):
        return self.wc_view.wc_graph_frame

    @property
    def integration_frame(self):
        return self.integration_view.frame

    @property
    def phase2_file_var(self):
        return self.integration_view.phase2_file_var

    @property
    def phase3_file_var(self):
        return self.integration_view.phase3_file_var

    @property
    def bathy_file_var(self):
        return self.integration_view.bathy_file_var

    @property
    def btn_run_integration(self):
        return self.integration_view.btn_run_integration

    @property
    def results_text(self):
        return self.integration_view.results_text

    @property
    def btn_export_master(self):
        return self.integration_view.btn_export_master

    def browse_file(self, string_var):
        return self.wc_view.browse_file(string_var)

    def browse_basin_file(self):
        return self.rusle_view.browse_basin_file()

    def browse_zonal(self):
        return self.rusle_view.browse_zonal()

    def execute_rusle_analysis(self):
        return self.rusle_view.execute_rusle_analysis()

    def export_yield_results_csv(self):
        return self.rusle_view.export_yield_results_csv()

    def execute_wc_analysis(self):
        return self.wc_view.execute_wc_analysis()

    def display_wc_summary_table(self):
        return self.wc_view.display_wc_summary_table()

    def export_wc_summary_csv(self):
        return self.wc_view.export_wc_summary_csv()

    def export_phase3_csv(self):
        return self.wc_view.export_phase3_csv()

    def execute_integration(self):
        return self.integration_view.execute_integration()

    def export_master_dataset(self):
        return self.integration_view.export_master_dataset()
