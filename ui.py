import threading

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import Patch

import pandas as pd

from paths import load_raster_matrix, read_table, resource_path
from reporter import IntegrationModule
from rusle_engine import SpatialProcessor, YieldCalculator
from wilcock_engine import BedloadVisualizer, FractionalModel, TimeSeriesAggregator


class SedimentApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Automated Sediment Analysis Software")
        self.root.geometry("980x720")

        self.spatial = SpatialProcessor()
        self.yield_calc = YieldCalculator()
        self.raster_array = None
        self.rgb_raster = None
        self.rusle_metrics = None
        self.rusle_row_metrics = None
        self.rusle_results_df = None
        self._cell_editor = None
        self._edit_iid = None
        self._edit_col_idx = None
        self.phase2_df = None
        self.phase3_df = None
        self.annual_summary = None
        self.final_merged_df = None
        self._wc_plot_window = None
        self._wc_fig = None
        self._rusle_preview_window = None
        self._rusle_preview_fig = None
        self._wc_running = False

        self.load_startup_data()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=10)

        self.setup_rusle_tab()
        self.setup_wc_tab()
        self.setup_integration_tab()

    def load_startup_data(self):
        self.default_basin_path = ""
        self.default_raster_path = ""

    def setup_rusle_tab(self):
        self.rusle_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.rusle_frame, text="RUSLE Spatial Engine")

        # Bulk-edit basin grid (replaces basin/sub-basin dropdowns, Area/Slope vars, Reporting Year).
        ttk.Button(self.rusle_frame, text="Browse Basin File", command=self.browse_basin_file).grid(
            row=0, column=0, padx=5, pady=6, sticky="w"
        )
        self.basin_file_var = tk.StringVar(value=getattr(self, "default_basin_path", ""))
        ttk.Entry(self.rusle_frame, textvariable=self.basin_file_var, width=50, state="readonly").grid(
            row=0, column=1, padx=5, pady=6, sticky="ew"
        )

        tree_wrap = ttk.Frame(self.rusle_frame)
        tree_wrap.grid(row=1, column=0, columnspan=3, padx=5, pady=6, sticky="nsew")
        columns = ("dam", "basin", "subbasin", "year", "area", "slope")
        self.basin_tree = ttk.Treeview(tree_wrap, columns=columns, show="headings", height=10)
        headings = {
            "dam": "Dam Name",
            "basin": "Basin",
            "subbasin": "Sub-Basin",
            "year": "Year",
            "area": "Area",
            "slope": "Slope",
        }
        for col, title in headings.items():
            self.basin_tree.heading(col, text=title)
            self.basin_tree.column(col, width=130, stretch=True, anchor="center")
        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.basin_tree.yview)
        self.basin_tree.configure(yscrollcommand=tree_scroll.set)
        self.basin_tree.pack(side=tk.LEFT, fill="both", expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill="y")
        self.basin_tree.bind("<Double-1>", self._on_basin_tree_double_click)

        # Place the raster browse button in the left column (replacing the label)
        self.raster_file_var = tk.StringVar(value=getattr(self, "default_raster_path", ""))
        ttk.Button(self.rusle_frame, text="Browse Raster CSV", command=self.browse_raster).grid(
            row=2, column=0, padx=5, pady=6, sticky="w"
        )
        ttk.Entry(self.rusle_frame, textvariable=self.raster_file_var, width=50, state="readonly").grid(
            row=2, column=1, padx=5, pady=6, sticky="ew"
        )

        button_row = ttk.Frame(self.rusle_frame)
        button_row.grid(row=3, column=0, columnspan=3, pady=12)
        ttk.Button(button_row, text="Classify & Compute Yield", command=self.execute_rusle_analysis).pack(
            side=tk.LEFT, padx=6
        )
        self.btn_export_tif = ttk.Button(
            button_row, text="Export Color-Coded .tif", command=self.export_color_tif, state="disabled"
        )
        self.btn_export_tif.pack(side=tk.LEFT, padx=6)
        self.btn_export_phase2 = ttk.Button(
            button_row, text="Export Yield Results CSV", command=self.export_yield_results_csv, state="disabled"
        )
        self.btn_export_phase2.pack(side=tk.LEFT, padx=6)

        results_wrap = ttk.Frame(self.rusle_frame)
        results_wrap.grid(row=4, column=0, columnspan=3, padx=10, pady=8, sticky="nsew")

        cols = ("dam", "basin", "subbasin", "year", "usda_scs_sio", "cem_sio", "avg_sio", "yield_t_yr", "volume_m3_yr", "sp_yield_m3_yr_km2")
        self.results_tree = ttk.Treeview(results_wrap, columns=cols, show="headings", height=8)
        self.results_tree.heading("dam", text="Dam Name")
        self.results_tree.heading("basin", text="Basin")
        self.results_tree.heading("subbasin", text="Sub-Basin")
        self.results_tree.heading("year", text="Year")
        self.results_tree.heading("usda_scs_sio", text="USDA-SCS SIO")
        self.results_tree.heading("cem_sio", text="CEM SIO")
        self.results_tree.heading("avg_sio", text="Average SIO")
        self.results_tree.heading("yield_t_yr", text="Transported Mass (t/yr)")
        self.results_tree.heading("volume_m3_yr", text="Transported Volume (m³/yr)")
        self.results_tree.heading("sp_yield_m3_yr_km2", text="Specific Yield (m³/yr/km²)")

        # reasonable column sizing
        self.results_tree.column("dam", width=180, anchor="w")
        self.results_tree.column("basin", width=180, anchor="w")
        self.results_tree.column("subbasin", width=180, anchor="w")
        self.results_tree.column("year", width=80, anchor="center")
        self.results_tree.column("yield_t_yr", width=120, anchor="e")
        self.results_tree.column("volume_m3_yr", width=140, anchor="e")
        self.results_tree.column("sp_yield_m3_yr_km2", width=160, anchor="e")
        self.results_tree.column("usda_scs_sio", width=120, anchor="e")
        self.results_tree.column("cem_sio", width=100, anchor="e")
        self.results_tree.column("avg_sio", width=110, anchor="e")

        results_scroll = ttk.Scrollbar(results_wrap, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=results_scroll.set)
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        results_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.rusle_frame.columnconfigure(1, weight=1)
        self.rusle_frame.rowconfigure(1, weight=1)
        self.rusle_frame.rowconfigure(4, weight=1)

    def setup_wc_tab(self):
        self.wc_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.wc_frame, text="Wilcock & Crowe Bedload")
        # allow the file-entry column to expand horizontally
        self.wc_frame.columnconfigure(1, weight=1)
        self.flow_file_var = tk.StringVar()
        self.frac_file_var = tk.StringVar()

        ttk.Button(self.wc_frame, text="Browse Daily Flow CSV", command=lambda: self.browse_file(self.flow_file_var)).grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )
        ttk.Entry(self.wc_frame, textvariable=self.flow_file_var, width=50, state="readonly").grid(
            row=0, column=1, padx=10, pady=10, sticky="ew"
        )

        ttk.Button(
            self.wc_frame, text="Browse Fractional CSV", command=lambda: self.browse_file(self.frac_file_var)
        ).grid(row=1, column=0, padx=10, pady=10, sticky="w")
        ttk.Entry(self.wc_frame, textvariable=self.frac_file_var, width=50, state="readonly").grid(
            row=1, column=1, padx=10, pady=10, sticky="ew"
        )

        wc_buttons = ttk.Frame(self.wc_frame)
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

        self.wc_status_var = tk.StringVar(value="Idle")
        ttk.Label(self.wc_frame, textvariable=self.wc_status_var).grid(row=3, column=0, columnspan=2, pady=4)
        # Inline graph container (will hold the embedded Matplotlib canvas)
        self.wc_graph_frame = ttk.Frame(self.wc_frame)
        self.wc_graph_frame.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=10, pady=6)
        self.wc_frame.rowconfigure(4, weight=1)

    def setup_integration_tab(self):
        self.integration_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.integration_frame, text="Integration & Handoff")

        # allow the second column (entry widgets) to expand horizontally
        # keep the left column (buttons) fixed so entries stretch from button to window edge
        self.integration_frame.columnconfigure(0, weight=0)
        self.integration_frame.columnconfigure(1, weight=1)

        self.phase2_file_var = tk.StringVar()
        self.phase3_file_var = tk.StringVar()
        self.bathy_file_var = tk.StringVar()

        ttk.Button(
            self.integration_frame,
            text="Browse Phase 2 Output (CSV)",
            command=lambda: self.browse_file(self.phase2_file_var),
        ).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        ttk.Entry(self.integration_frame, textvariable=self.phase2_file_var, width=50, state="readonly").grid(
            row=0, column=1, padx=10, pady=5, sticky="ew"
        )

        ttk.Button(
            self.integration_frame,
            text="Browse Phase 3 Output (CSV)",
            command=lambda: self.browse_file(self.phase3_file_var),
        ).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        ttk.Entry(self.integration_frame, textvariable=self.phase3_file_var, width=50, state="readonly").grid(
            row=1, column=1, padx=10, pady=5, sticky="ew"
        )

        ttk.Button(
            self.integration_frame,
            text="Browse Bathymetry (Optional)",
            command=lambda: self.browse_file(self.bathy_file_var),
        ).grid(row=2, column=0, padx=10, pady=5, sticky="w")
        ttk.Entry(self.integration_frame, textvariable=self.bathy_file_var, width=50, state="readonly").grid(
            row=2, column=1, padx=10, pady=5, sticky="ew"
        )

        self.btn_run_integration = ttk.Button(
            self.integration_frame, text="Merge Data & Find Extremes", command=self.execute_integration
        )
        self.btn_run_integration.grid(row=3, column=0, columnspan=2, pady=10)

        self.results_text = tk.Text(self.integration_frame, height=10, width=70, state="disabled")
        self.results_text.grid(row=4, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")
        self.integration_frame.rowconfigure(4, weight=1)

        self.btn_export_master = ttk.Button(
            self.integration_frame,
            text="Export Master Dataset (Excel)",
            command=self.export_master_dataset,
            state="disabled",
        )
        self.btn_export_master.grid(row=5, column=0, columnspan=2, pady=10)

    def browse_file(self, string_var):
        filepath = filedialog.askopenfilename(
            filetypes=[("CSV/Excel Files", "*.csv *.xlsx *.xls"), ("All Files", "*.*")]
        )
        if filepath:
            string_var.set(filepath)

    def browse_basin_file(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("CSV/Excel Files", "*.csv *.xlsx *.xls"), ("All Files", "*.*")]
        )
        if filepath:
            self._populate_basin_tree(filepath, show_errors=True)

    def _populate_basin_tree(self, file_path: str, show_errors: bool = False):
        try:
            df = read_table(file_path)
            required = ["Basin Name", "Sub-basin Name"]
            missing = [col for col in required if col not in df.columns]
            if missing:
                raise KeyError(f"Basin table missing columns: {missing}")

            for child in self.basin_tree.get_children():
                self.basin_tree.delete(child)

            year = 2026
            work = df.reset_index(drop=True)
            areas = pd.to_numeric(work["Area"], errors="coerce") if "Area" in work.columns else pd.Series(dtype=float)
            slopes = (
                pd.to_numeric(work["Main Waterway Slope"], errors="coerce")
                if "Main Waterway Slope" in work.columns
                else pd.Series(dtype=float)
            )

            for idx, row in work.iterrows():
                dam_name = row["Dam Name"] if "Dam Name" in work.columns else ""
                basin = row["Basin Name"]
                subbasin = row["Sub-basin Name"]
                if pd.isna(basin) or pd.isna(subbasin):
                    continue
                area_val = areas.iloc[idx] if idx < len(areas) else pd.NA
                slope_val = slopes.iloc[idx] if idx < len(slopes) else pd.NA
                area_text = "" if pd.isna(area_val) else str(float(area_val))
                slope_text = "" if pd.isna(slope_val) else str(float(slope_val))
                self.basin_tree.insert(
                    "",
                    "end",
                    values=(str(dam_name), str(basin), str(subbasin), str(year), area_text, slope_text),
                )

            self.basin_file_var.set(file_path)
        except Exception as exc:
            if show_errors:
                messagebox.showerror("Basin File Error", f"Could not load basin table:\n\n{exc}")
            else:
                raise

    def _destroy_cell_editor(self):
        editor = self._cell_editor
        self._cell_editor = None
        self._edit_iid = None
        self._edit_col_idx = None
        if editor is not None:
            editor.destroy()

    def _on_basin_tree_double_click(self, event):
        if self.basin_tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.basin_tree.identify_row(event.y)
        col_id = self.basin_tree.identify_column(event.x)
        if not iid or not col_id:
            return
        col_idx = int(col_id.replace("#", "")) - 1
        columns = self.basin_tree["columns"]
        if col_idx < 0 or col_idx >= len(columns):
            return
        if columns[col_idx] not in ("year", "area", "slope"):
            return

        bbox = self.basin_tree.bbox(iid, col_id)
        if not bbox:
            return
        x, y, width, height = bbox

        self._destroy_cell_editor()
        values = list(self.basin_tree.item(iid, "values"))
        editor = ttk.Entry(self.basin_tree)
        editor.insert(0, values[col_idx] if col_idx < len(values) else "")
        editor.place(x=x, y=y, width=width, height=height)
        editor.focus_set()
        editor.select_range(0, tk.END)

        self._cell_editor = editor
        self._edit_iid = iid
        self._edit_col_idx = col_idx
        editor.bind("<Return>", self._commit_cell_edit)
        editor.bind("<FocusOut>", self._commit_cell_edit)
        editor.bind("<Escape>", self._cancel_cell_edit)

    def _commit_cell_edit(self, event=None):
        if self._cell_editor is None or self._edit_iid is None or self._edit_col_idx is None:
            return
        iid = self._edit_iid
        col_idx = self._edit_col_idx
        new_value = self._cell_editor.get()
        values = list(self.basin_tree.item(iid, "values"))
        while len(values) < 6:
            values.append("")
        values[col_idx] = new_value
        self.basin_tree.item(iid, values=values)
        self._destroy_cell_editor()

    def _cancel_cell_edit(self, event=None):
        self._destroy_cell_editor()

    def browse_raster(self):
        filepath = filedialog.askopenfilename(filetypes=[("CSV Matrices", "*.csv"), ("All Files", "*.*")])
        if not filepath:
            return
        try:
            self.raster_array = load_raster_matrix(filepath)
            self.raster_file_var.set(filepath)
            self.rgb_raster = None
            self.btn_export_tif.config(state="disabled")
        except Exception as exc:
            messagebox.showerror("Raster Error", f"Could not load raster matrix:\n\n{exc}")

    def _iter_basin_rows(self):
        if self.raster_array is None:
            raise ValueError("Load a headerless raster matrix CSV first.")
        children = self.basin_tree.get_children()
        if not children:
            raise ValueError("Import a basin file so the grid has at least one row.")

        rows = []
        for iid in children:
            values = list(self.basin_tree.item(iid, "values"))
            while len(values) < 6:
                values.append("")
            dam_name, basin, subbasin, year_s, area_s, slope_s = values[:6]
            if not str(slope_s).strip():
                raise ValueError(f"Slope (m/m) is required for {basin} / {subbasin}.")
            year = int(year_s)
            area_km2 = float(area_s)
            slope = float(slope_s)
            if area_km2 <= 0:
                raise ValueError(f"Basin area must be greater than zero for {basin} / {subbasin}.")
            rows.append((str(dam_name), str(basin), str(subbasin), year, area_km2, slope))
        return rows

    def execute_rusle_analysis(self):
        try:
            basin_rows = self._iter_basin_rows()
            mean_t_ha = self.yield_calc.raster_mean_t_ha_yr(self.raster_array)
            self.rgb_raster = self.spatial.apply_5_class_colormap(self.raster_array)

            row_metrics = []
            handoff_frames = []
            for dam_name, basin, subbasin, year, area_km2, slope in basin_rows:
                metrics = self.yield_calc.calculate_metrics(mean_t_ha, area_km2, slope)
                row_metrics.append(
                    {
                        "dam": dam_name,
                        "basin": basin,
                        "subbasin": subbasin,
                        "year": year,
                        "area_km2": area_km2,
                        "slope": slope,
                        **metrics,
                    }
                )
                handoff_frames.append(self.yield_calc.to_phase2_handoff(year, metrics["volume_m3"]))


            self.rusle_row_metrics = row_metrics
            self.rusle_results_df = pd.DataFrame(row_metrics)
            self.rusle_metrics = row_metrics[0] if row_metrics else None
            self.phase2_df = (
                pd.concat(handoff_frames, ignore_index=True)
                .groupby("Year", as_index=False)["Suspended_Volume_m3"]
                .sum()
            )
            self.btn_export_tif.config(state="normal")
            self.btn_export_phase2.config(state="normal")
            self._write_rusle_results()
            self._show_rusle_preview()
        except Exception as exc:
            messagebox.showerror("RUSLE Error", str(exc))

    def _write_rusle_results(self):
        rows = self.rusle_row_metrics or []
        if not rows:
            return
        # clear existing tree rows
        try:
            self.results_tree.delete(*self.results_tree.get_children())
        except Exception:
            pass

        # Insert computed rows into the grid, rounding numeric values to 2 decimals
        for m in rows:
            dam = m.get("dam", "")
            basin = m.get("basin", "")
            subbasin = m.get("subbasin", "")
            year = m.get("year", "")
            usda_sio = m.get("usda_scs_sio", 0.0)
            cem_sio = m.get("cem_sio", 0.0)
            avg_sio = m.get("avg_sio", 0.0)
            mass = m.get("yield_mass_t", 0.0)
            volume = m.get("volume_m3", 0.0)
            sp_yield = m.get("specific_yield_m3_km2", 0.0)

            self.results_tree.insert(
                "",
                "end",
                values=(
                    dam,
                    basin,
                    subbasin,
                    year,
                    f"{usda_sio:.4f}",
                    f"{cem_sio:.4f}",
                    f"{avg_sio:.4f}",
                    f"{mass:.2f}",
                    f"{volume:.2f}",
                    f"{sp_yield:.2f}",
                ),
            )

    def _show_rusle_preview(self):
        if self._rusle_preview_window is not None and self._rusle_preview_window.winfo_exists():
            self._rusle_preview_window.destroy()
        if self._rusle_preview_fig is not None:
            plt.close(self._rusle_preview_fig)

        self._rusle_preview_fig, ax = plt.subplots(figsize=(6.5, 4.5))
        ax.imshow(self.rgb_raster)
        ax.set_title("5-class RGB preview")
        ax.axis("off")

        class_labels = [
            "Class 1: <= 1",
            "Class 2: 1-5",
            "Class 3: 5-10",
            "Class 4: 10-20",
            "Class 5: > 20",
        ]
        legend_handles = [
            Patch(
                facecolor=np.array(self.spatial.colormap_5_class[class_id]) / 255.0,
                edgecolor="black",
                linewidth=0.5,
                label=label,
            )
            for class_id, label in zip(range(1, 6), class_labels)
        ]
        legend = ax.legend(
            handles=legend_handles,
            title="Erosion class",
            loc="center left",
            bbox_to_anchor=(1.0, 0.5),
            frameon=True,
        )
        legend.get_frame().set_facecolor("white")
        legend.get_frame().set_alpha(0.9)

        self._rusle_preview_fig.subplots_adjust(right=0.78)
        self._rusle_preview_fig.tight_layout()

        self._rusle_preview_window = tk.Toplevel(self.root)
        self._rusle_preview_window.title("RUSLE Color Map")
        canvas = FigureCanvasTkAgg(self._rusle_preview_fig, master=self._rusle_preview_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def export_color_tif(self):
        if self.rgb_raster is None:
            messagebox.showerror("Export Error", "Run Classify & Compute Yield first.")
            return
        save_path = filedialog.asksaveasfilename(
            title="Save Color-Coded Raster",
            defaultextension=".tif",
            filetypes=[("TIFF Image", "*.tif *.tiff"), ("PNG Image", "*.png")],
        )
        if save_path:
            try:
                self.spatial.export_rgb_tiff(self.rgb_raster, save_path)
                messagebox.showinfo("Success", f"RGB raster saved to:\n{save_path}")
            except Exception as exc:
                messagebox.showerror("Export Error", str(exc))

    def export_yield_results_csv(self):
        if self.rusle_results_df is None or self.rusle_results_df.empty:
            messagebox.showerror("Export Error", "Run Classify & Compute Yield first.")
            return
        save_path = filedialog.asksaveasfilename(
            title="Save Yield Results CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if save_path:
            export_df = self.rusle_results_df[
                [
                    "dam",
                    "basin",
                    "subbasin",
                    "year",
                    "area_km2",
                    "slope",
                    "usda_scs_sio",
                    "cem_sio",
                    "avg_sio",
                    "yield_mass_t",
                    "volume_m3",
                    "specific_yield_m3_km2",
                ]
            ].copy()
            export_df = export_df.rename(
                columns={
                    "dam": "Dam",
                    "basin": "Basin",
                    "subbasin": "Sub-Basin",
                    "year": "Year",
                    "area_km2": "Area_km2",
                    "slope": "Slope_m_per_m",
                    "usda_scs_sio": "USDA-SCS_SIO",
                    "cem_sio": "CEM_SIO",
                    "avg_sio": "Average_SIO",
                    "yield_mass_t": "Yield_t_yr",
                    "volume_m3": "Transported_Volume_m3_yr",
                    "specific_yield_m3_km2": "Specific_Yield_m3_yr_km2",
                }
            )
            export_df.to_csv(save_path, index=False)
            messagebox.showinfo("Success", f"Yield results saved to:\n{save_path}")

    def display_wc_summary_table(self):
        if self.annual_summary is None or self.annual_summary.empty:
            messagebox.showerror("Summary Error", "Run the Wilcock analysis first.")
            return

        self._clear_wc_display()
        summary_df = BedloadVisualizer.prepare_summary_table(self.annual_summary)
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
        if self.annual_summary is None or self.annual_summary.empty:
            messagebox.showerror("Graph Error", "Run the Wilcock analysis first.")
            return

        self._clear_wc_display()
        try:
            visualizer = BedloadVisualizer()
            fig = visualizer.generate_trend_graph(self.annual_summary)
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
        if self.annual_summary is None or self.annual_summary.empty:
            messagebox.showerror("Export Error", "Run the Wilcock analysis first.")
            return

        save_path = filedialog.asksaveasfilename(
            title="Save Annual Summary CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if save_path:
            try:
                BedloadVisualizer.export_summary_csv(self.annual_summary, save_path)
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
            self.root.after(0, lambda p=payload: self._on_wc_complete(*p))

        threading.Thread(target=worker, daemon=True).start()

    def _on_wc_complete(self, annual_summary, phase3_df, error):
        self._wc_running = False
        self.btn_export_png.config(state="normal")
        if error is not None:
            self.wc_status_var.set("Failed")
            messagebox.showerror("Analysis Error", f"An error occurred during calculation:\n\n{error}")
            return

        self.annual_summary = annual_summary
        self.phase3_df = phase3_df
        self.btn_export_phase3.config(state="normal")
        self.btn_export_summary.config(state="normal")

        self._render_wc_graph()

    def export_phase3_csv(self):
        if self.phase3_df is None:
            messagebox.showerror("Export Error", "Run the Wilcock analysis first.")
            return
        save_path = filedialog.asksaveasfilename(
            title="Save Phase 3 (Bedload Volume)",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if save_path:
            self.phase3_df.to_csv(save_path, index=False)
            self.phase3_file_var.set(save_path)
            messagebox.showinfo("Success", f"Phase 3 handoff saved to:\n{save_path}")

    def execute_integration(self):
        p2_path = self.phase2_file_var.get()
        p3_path = self.phase3_file_var.get()
        bathy_path = self.bathy_file_var.get()

        if not p2_path or not p3_path:
            messagebox.showerror("Input Error", "Phase 2 and Phase 3 datasets are required.")
            return

        try:
            df_p2 = read_table(p2_path)
            df_p3 = read_table(p3_path)
            df_bathy = read_table(bathy_path) if bathy_path else None

            integration = IntegrationModule()
            self.final_merged_df, join_warning = integration.merge_sediment_data(df_p2, df_p3)
            min_record, max_record = integration.locate_extremes(self.final_merged_df)

            interp_warnings = []
            if df_bathy is not None:
                min_record, max_record, interp_warnings = integration.generate_final_report_metrics(
                    min_record, max_record, df_bathy
                )

            self.results_text.config(state="normal")
            self.results_text.delete(1.0, tk.END)

            report = f"--- Minimum Volume Year: {min_record['Year']} ---\nTotal Volume: {min_record['Total_Volume_m3']:,.2f} m³\n"
            if "Interpolated_Elevation_m" in min_record:
                report += f"Reservoir Elevation: {min_record['Interpolated_Elevation_m']} m\n"
            report += f"\n--- Maximum Volume Year: {max_record['Year']} ---\nTotal Volume: {max_record['Total_Volume_m3']:,.2f} m³\n"
            if "Interpolated_Elevation_m" in max_record:
                report += f"Reservoir Elevation: {max_record['Interpolated_Elevation_m']} m\n"
            if join_warning:
                report += f"\n{join_warning}\n"
            for warning in interp_warnings:
                report += f"\n{warning}\n"

            self.results_text.insert(tk.END, report)
            self.results_text.config(state="disabled")
            self.btn_export_master.config(state="normal")
            if join_warning or interp_warnings:
                messagebox.showwarning("Integration Notes", "\n".join(filter(None, [join_warning] + interp_warnings)))
        except Exception as exc:
            messagebox.showerror("Integration Error", f"Failed to merge datasets:\n\n{exc}")

    def export_master_dataset(self):
        if self.final_merged_df is None or self.final_merged_df.empty:
            return
        save_path = filedialog.asksaveasfilename(
            title="Save Master Dataset", defaultextension=".xlsx", filetypes=[("Excel Files", "*.xlsx")]
        )
        if save_path:
            try:
                self.final_merged_df.to_excel(save_path, index=False)
                messagebox.showinfo("Success", f"Master Dataset saved to:\n{save_path}")
            except Exception as exc:
                messagebox.showerror("Export Error", f"Failed to save file:\n\n{exc}")
