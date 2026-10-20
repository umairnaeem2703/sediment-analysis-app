import tkinter as tk
from tkinter import ttk

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from src.core.monthly_flow_preprocessor import (
    DEFAULT_SEED,
    DEFAULT_SIGMA,
    MonthlyFlowPreprocessor,
    is_monthly_flow_table,
    prepare_daily_flow,
)
from src.core.wilcock import (
    BEDLOAD_COLUMN_LABEL,
    FLOW_COLUMN_LABEL,
    WATER_YEAR_COLUMN,
    YEAR_COLUMN,
    BedloadVisualizer,
    FractionalModel,
    TimeSeriesAggregator,
)
from src.ui.common import (
    browse_open_file,
    browse_save_file,
    run_in_background,
    show_error,
    show_info,
    show_warning,
)
from src.utils.paths import read_table

WATER_YEAR_HEADING = "Water Year (Oct–Sep)"


def _parse_dsi_settings(sigma_text: str, seed_text: str):
    """Parse the DSI σ/seed fields (a decimal comma is accepted). Raises ValueError if invalid."""
    try:
        pre = MonthlyFlowPreprocessor(sigma=float(sigma_text.strip().replace(",", ".")), seed=int(seed_text.strip()))
    except ValueError:
        raise ValueError("σ must be a finite number >= 0 and seed a whole number >= 0.") from None
    return pre.sigma, pre.seed


class WilcockView:
    def __init__(self, parent_notebook: ttk.Notebook, app_controller):
        self.notebook = parent_notebook
        self.app = app_controller
        self.frame = ttk.Frame(self.notebook)
        self.notebook.add(self.frame, text="Wilcock & Crowe Bedload")

        self.flow_file_var = tk.StringVar()
        self.frac_file_var = tk.StringVar()
        self.wc_status_var = tk.StringVar(value="Idle")
        self._wc_running = False
        self._wc_fig = None

        self._setup_ui()

    def _setup_ui(self):
        self.frame.columnconfigure(1, weight=1)

        ttk.Button(self.frame, text="Browse Flow CSV (daily or DSI monthly)", command=lambda: self.browse_file(self.flow_file_var)).grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )
        ttk.Entry(self.frame, textvariable=self.flow_file_var, width=50, state="readonly").grid(
            row=0, column=1, padx=10, pady=10, sticky="ew"
        )

        ttk.Button(
            self.frame, text="Browse Fractional CSV", command=lambda: self.browse_file(self.frac_file_var)
        ).grid(row=1, column=0, padx=10, pady=10, sticky="w")
        ttk.Entry(self.frame, textvariable=self.frac_file_var, width=50, state="readonly").grid(
            row=1, column=1, padx=10, pady=10, sticky="ew"
        )

        settings = ttk.Frame(self.frame)
        settings.grid(row=2, column=0, columnspan=2, pady=(0, 4))
        ttk.Label(settings, text="DSI monthly files only — σ:").pack(side=tk.LEFT, padx=(6, 2))
        self.sigma_var = tk.StringVar(value=str(DEFAULT_SIGMA))
        ttk.Entry(settings, textvariable=self.sigma_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(settings, text="seed:").pack(side=tk.LEFT, padx=(12, 2))
        self.seed_var = tk.StringVar(value=str(DEFAULT_SEED))
        ttk.Entry(settings, textvariable=self.seed_var, width=6).pack(side=tk.LEFT, padx=2)

        wc_buttons = ttk.Frame(self.frame)
        wc_buttons.grid(row=3, column=0, columnspan=2, pady=12)
        self.btn_export_png = ttk.Button(
            wc_buttons, text="Execute & Export Trend Graph", command=self.execute_wc_analysis
        )
        self.btn_export_png.pack(side=tk.LEFT, padx=6)
        self.btn_show_summary = ttk.Button(
            wc_buttons, text="Display Summary Table", command=self.display_wc_summary_table
        )
        self.btn_show_summary.pack(side=tk.LEFT, padx=6)
        self.btn_export_summary = ttk.Button(
            wc_buttons, text="Export Summary CSV", command=self.export_wc_summary_csv, state="disabled"
        )
        self.btn_export_summary.pack(side=tk.LEFT, padx=6)

        ttk.Label(self.frame, textvariable=self.wc_status_var).grid(row=4, column=0, columnspan=2, pady=4)

        self.wc_graph_frame = ttk.Frame(self.frame)
        self.wc_graph_frame.grid(row=5, column=0, columnspan=2, sticky="nsew", padx=10, pady=6)
        self.frame.rowconfigure(5, weight=1)

    def browse_file(self, string_var):
        filepath = browse_open_file(title="Select CSV/Excel File")
        if filepath:
            string_var.set(filepath)

    def display_wc_summary_table(self):
        if self.app.annual_summary is None or self.app.annual_summary.empty:
            show_error("Summary Error", "Run the Wilcock analysis first.")
            return

        self._clear_wc_display()
        summary_df = BedloadVisualizer.prepare_summary_table(self.app.annual_summary)
        columns = list(summary_df.columns)
        tree = ttk.Treeview(self.wc_graph_frame, columns=columns, show="headings", height=max(8, min(15, len(summary_df))))
        for col in columns:
            heading = WATER_YEAR_HEADING if col == WATER_YEAR_COLUMN else col
            tree.heading(col, text=heading)
            width = max(100, 8 * len(heading))
            tree.column(col, width=width, anchor="center")

        for _, row in summary_df.iterrows():
            values = []
            for col_name in columns:
                value = row[col_name]
                if col_name in (YEAR_COLUMN, WATER_YEAR_COLUMN):
                    values.append(int(value))
                elif col_name == FLOW_COLUMN_LABEL:
                    values.append(f"{float(value):.4f}")
                elif col_name == BEDLOAD_COLUMN_LABEL:
                    values.append(f"{float(value):,.2f}")
                else:
                    values.append(value)
            tree.insert("", "end", values=tuple(values))

        tree_scroll = ttk.Scrollbar(self.wc_graph_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=tree_scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.btn_export_summary.config(state="normal")
        self.wc_status_var.set("Summary table displayed.")

    def _clear_wc_display(self):
        for child in list(self.wc_graph_frame.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass

        if self._wc_fig is not None:
            try:
                plt.close(self._wc_fig)
            except Exception:
                pass
        self._wc_fig = None

    def _render_wc_graph(self):
        if self.app.annual_summary is None or self.app.annual_summary.empty:
            show_error("Graph Error", "Run the Wilcock analysis first.")
            return

        self._clear_wc_display()
        try:
            visualizer = BedloadVisualizer()
            fig = visualizer.generate_trend_graph(self.app.annual_summary)
        except Exception as exc:
            self.wc_status_var.set("Failed")
            show_error("Visualization Error", f"Could not generate plot:\n\n{exc}")
            return

        self._wc_fig = fig
        canvas = FigureCanvasTkAgg(fig, master=self.wc_graph_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        def save_fig():
            save_path = browse_save_file(
                title="Save Trend Graph", defaultextension=".png", filetypes=[("PNG Image", "*.png")]
            )
            if save_path:
                try:
                    fig.savefig(save_path, dpi=300, bbox_inches="tight")
                    show_info("Success", f"Graph successfully saved to:\n{save_path}")
                except Exception as exc:
                    show_error("Export Error", str(exc))

        ttk.Button(self.wc_graph_frame, text="Export as PNG", command=save_fig).pack(pady=6)
        self.wc_status_var.set("Graph displayed.")

    def export_wc_summary_csv(self):
        if self.app.annual_summary is None or self.app.annual_summary.empty:
            show_error("Export Error", "Run the Wilcock analysis first.")
            return

        save_path = browse_save_file(
            title="Save Annual Summary CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if save_path:
            try:
                BedloadVisualizer.export_summary_csv(self.app.annual_summary, save_path)
                show_info("Success", f"Annual summary saved to:\n{save_path}")
            except Exception as exc:
                show_error("Export Error", str(exc))

        self.wc_status_var.set("Summary exported.")

    def execute_wc_analysis(self):
        if self._wc_running:
            return
        flow_path = self.flow_file_var.get()
        frac_path = self.frac_file_var.get()
        if not flow_path or not frac_path:
            show_error("Input Error", "Please browse and select both the Flow and Fractional Data files.")
            return

        # Read on the Tk thread; only parsed (and validated) if the flow file turns out to be DSI monthly.
        sigma_text = self.sigma_var.get()
        seed_text = self.seed_var.get()

        self._wc_running = True
        self.btn_export_png.config(state="disabled")
        self.btn_export_summary.config(state="disabled")
        self.wc_status_var.set("Running daily bedload on a background thread...")

        def computation_task():
            df_flow = read_table(flow_path)
            df_frac = read_table(frac_path)
            notes = []
            if is_monthly_flow_table(df_flow):
                # The converted series carries a Water_Year column, so the aggregator groups by water year.
                sigma, seed = _parse_dsi_settings(sigma_text, seed_text)
                df_flow, notes = prepare_daily_flow(df_flow, sigma=sigma, seed=seed)
            model = FractionalModel()
            model.load_fractional_parameters(df_frac)
            aggregator = TimeSeriesAggregator(model)
            annual_summary = aggregator.process_annual_averages(df_flow)
            phase3_df = aggregator.to_phase3_handoff(annual_summary)
            self._wc_warnings = notes + list(aggregator.warnings)
            return annual_summary, phase3_df

        def on_complete(result, error):
            self._wc_running = False
            self.btn_export_png.config(state="normal")
            if error is not None:
                self.wc_status_var.set("Failed")
                show_error("Analysis Error", f"An error occurred during calculation:\n\n{error}")
                return

            annual_summary, phase3_df = result
            self.app.set_wilcock_results(annual_summary, phase3_df)
            self.btn_export_summary.config(state="normal")
            self._render_wc_graph()
            warnings = getattr(self, "_wc_warnings", [])
            if warnings:
                show_warning("Flow Data Notes", "\n".join(warnings))

        run_in_background(self.app.root, computation_task, on_complete)


