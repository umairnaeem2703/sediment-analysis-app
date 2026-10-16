import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from src.core.wilcock import BedloadVisualizer, FractionalModel, TimeSeriesAggregator
from src.utils.paths import read_table


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

        ttk.Button(self.frame, text="Browse Daily Flow CSV", command=lambda: self.browse_file(self.flow_file_var)).grid(
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

        wc_buttons = ttk.Frame(self.frame)
        wc_buttons.grid(row=2, column=0, columnspan=2, pady=12)
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
        self.btn_export_phase3 = ttk.Button(
            wc_buttons, text="Export Phase 3 CSV", command=self.export_phase3_csv, state="disabled"
        )
        self.btn_export_phase3.pack(side=tk.LEFT, padx=6)

        ttk.Label(self.frame, textvariable=self.wc_status_var).grid(row=3, column=0, columnspan=2, pady=4)

        self.wc_graph_frame = ttk.Frame(self.frame)
        self.wc_graph_frame.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=10, pady=6)
        self.frame.rowconfigure(4, weight=1)

    def browse_file(self, string_var):
        filepath = filedialog.askopenfilename(
            filetypes=[("CSV/Excel Files", "*.csv *.xlsx *.xls"), ("All Files", "*.*")]
        )
        if filepath:
            string_var.set(filepath)

    def display_wc_summary_table(self):
        if self.app.annual_summary is None or self.app.annual_summary.empty:
            messagebox.showerror("Summary Error", "Run the Wilcock analysis first.")
            return

        self._clear_wc_display()
        summary_df = BedloadVisualizer.prepare_summary_table(self.app.annual_summary)
        columns = list(summary_df.columns)
        tree = ttk.Treeview(self.wc_graph_frame, columns=columns, show="headings", height=max(8, min(15, len(summary_df))))
        for col in columns:
            tree.heading(col, text=col)
            width = 180 if "Flow" in col or "Bedload" in col else 100
            tree.column(col, width=width, anchor="center")

        for _, row in summary_df.iterrows():
            values = []
            for col_name in columns:
                value = row[col_name]
                if col_name == "Year":
                    values.append(int(value))
                elif "Flow" in col_name:
                    values.append(f"{float(value):.4f}")
                elif "Bedload" in col_name:
                    values.append(f"{float(value):.6f}")
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
            messagebox.showerror("Graph Error", "Run the Wilcock analysis first.")
            return

        self._clear_wc_display()
        try:
            visualizer = BedloadVisualizer()
            fig = visualizer.generate_trend_graph(self.app.annual_summary)
        except Exception as exc:
            self.wc_status_var.set("Failed")
            messagebox.showerror("Visualization Error", f"Could not generate plot:\n\n{exc}")
            return

        self._wc_fig = fig
        canvas = FigureCanvasTkAgg(fig, master=self.wc_graph_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        def save_fig():
            save_path = filedialog.asksaveasfilename(
                title="Save Trend Graph", defaultextension=".png", filetypes=[("PNG Image", "*.png")]
            )
            if save_path:
                try:
                    fig.savefig(save_path, dpi=300, bbox_inches="tight")
                    messagebox.showinfo("Success", f"Graph successfully saved to:\n{save_path}")
                except Exception as exc:
                    messagebox.showerror("Export Error", str(exc))

        ttk.Button(self.wc_graph_frame, text="Export as PNG", command=save_fig).pack(pady=6)
        self.wc_status_var.set("Graph displayed.")

    def export_wc_summary_csv(self):
        if self.app.annual_summary is None or self.app.annual_summary.empty:
            messagebox.showerror("Export Error", "Run the Wilcock analysis first.")
            return

        save_path = filedialog.asksaveasfilename(
            title="Save Annual Summary CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if save_path:
            try:
                BedloadVisualizer.export_summary_csv(self.app.annual_summary, save_path)
                messagebox.showinfo("Success", f"Annual summary saved to:\n{save_path}")
            except Exception as exc:
                messagebox.showerror("Export Error", str(exc))

        self.wc_status_var.set("Summary exported.")

    def execute_wc_analysis(self):
        if self._wc_running:
            return
        flow_path = self.flow_file_var.get()
        frac_path = self.frac_file_var.get()
        if not flow_path or not frac_path:
            messagebox.showerror("Input Error", "Please browse and select both the Flow and Fractional Data files.")
            return

        self._wc_running = True
        self.btn_export_png.config(state="disabled")
        self.btn_export_phase3.config(state="disabled")
        self.btn_export_summary.config(state="disabled")
        self.wc_status_var.set("Running daily bedload on a background thread...")

        def worker():
            try:
                df_flow = read_table(flow_path)
                df_frac = read_table(frac_path)
                model = FractionalModel()
                model.load_fractional_parameters(df_frac)
                aggregator = TimeSeriesAggregator(model)
                annual_summary = aggregator.process_annual_averages(df_flow)
                phase3_df = aggregator.to_phase3_handoff(annual_summary)
                payload = (annual_summary, phase3_df, None)
            except Exception as exc:
                payload = (None, None, exc)
            self.app.root.after(0, lambda p=payload: self._on_wc_complete(*p))

        threading.Thread(target=worker, daemon=True).start()

    def _on_wc_complete(self, annual_summary, phase3_df, error):
        self._wc_running = False
        self.btn_export_png.config(state="normal")
        if error is not None:
            self.wc_status_var.set("Failed")
            messagebox.showerror("Analysis Error", f"An error occurred during calculation:\n\n{error}")
            return

        self.app.annual_summary = annual_summary
        self.app.phase3_df = phase3_df
        self.btn_export_phase3.config(state="normal")
        self.btn_export_summary.config(state="normal")

        self._render_wc_graph()

    def export_phase3_csv(self):
        if self.app.phase3_df is None:
            messagebox.showerror("Export Error", "Run the Wilcock analysis first.")
            return
        save_path = filedialog.asksaveasfilename(
            title="Save Phase 3 (Bedload Volume)",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if save_path:
            self.app.phase3_df.to_csv(save_path, index=False)
            self.app.integration_view.phase3_file_var.set(save_path)
            messagebox.showinfo("Success", f"Phase 3 handoff saved to:\n{save_path}")
