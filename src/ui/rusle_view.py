import math
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

from src.utils.paths import read_table


class RusleView:
    def __init__(self, parent_notebook: ttk.Notebook, app_controller):
        self.notebook = parent_notebook
        self.app = app_controller
        self.frame = ttk.Frame(self.notebook)
        self.notebook.add(self.frame, text="RUSLE Spatial Engine")

        self._cell_editor = None
        self._edit_iid = None
        self._edit_col_idx = None

        self._setup_ui()

    def _setup_ui(self):
        # Bulk-edit basin grid
        ttk.Button(self.frame, text="Browse Basin File", command=self.browse_basin_file).grid(
            row=0, column=0, padx=5, pady=6, sticky="w"
        )
        self.basin_file_var = tk.StringVar(value=getattr(self.app, "default_basin_path", ""))
        ttk.Entry(self.frame, textvariable=self.basin_file_var, width=50, state="readonly").grid(
            row=0, column=1, padx=5, pady=6, sticky="ew"
        )

        tree_wrap = ttk.Frame(self.frame)
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

        # Zonal statistics file input
        self.zonal_file_var = tk.StringVar(value=getattr(self.app, "default_zonal_path", ""))
        ttk.Button(self.frame, text="Browse Zonal Statistics (CSV)", command=self.browse_zonal).grid(
            row=2, column=0, padx=5, pady=6, sticky="w"
        )
        ttk.Entry(self.frame, textvariable=self.zonal_file_var, width=50, state="readonly").grid(
            row=2, column=1, padx=5, pady=6, sticky="ew"
        )

        button_row = ttk.Frame(self.frame)
        button_row.grid(row=4, column=0, columnspan=3, pady=12)
        ttk.Button(button_row, text="Classify & Compute Yield", command=self.execute_rusle_analysis).pack(
            side=tk.LEFT, padx=6
        )
        self.btn_export_phase2 = ttk.Button(
            button_row, text="Export Yield Results CSV", command=self.export_yield_results_csv, state="disabled"
        )
        self.btn_export_phase2.pack(side=tk.LEFT, padx=6)

        results_wrap = ttk.Frame(self.frame)
        results_wrap.grid(row=5, column=0, columnspan=3, padx=10, pady=8, sticky="nsew")

        cols = (
            "dam",
            "basin",
            "subbasin",
            "year",
            "usda_scs_sio",
            "cem_sio",
            "avg_sio",
            "yield_t_yr",
            "volume_m3_yr",
            "sp_yield_m3_yr_km2",
        )
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

        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(1, weight=1)
        self.frame.rowconfigure(5, weight=1)

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
                self.basin_tree.insert("", "end", values=(dam_name, basin, subbasin, year, area_val, slope_val))
            self.basin_file_var.set(file_path)
        except Exception as exc:
            if show_errors:
                messagebox.showerror("Basin File Error", f"Could not load basin table:\n\n{exc}")
            else:
                raise
        self._destroy_cell_editor()

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

    def _destroy_cell_editor(self):
        if self._cell_editor is not None:
            try:
                self._cell_editor.destroy()
            except tk.TclError:
                pass
        self._cell_editor = None
        self._edit_iid = None
        self._edit_col_idx = None

    def browse_zonal(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("CSV/Excel Files", "*.csv *.xlsx *.xls"), ("All Files", "*.*")]
        )
        if filepath:
            self.zonal_file_var.set(filepath)

    @staticmethod
    def _normalize_subbasin_name(value):
        if value is None:
            return ""
        text = str(value).strip()
        if text == "":
            return ""
        lower = text.lower()
        try:
            numeric_value = float(lower)
        except ValueError:
            numeric_value = None

        if numeric_value is not None and math.isfinite(numeric_value):
            if numeric_value.is_integer():
                return str(int(numeric_value))
            return format(numeric_value, "g")

        normalized = "".join(ch for ch in lower if ch.isalnum())
        for prefix in ("subbasin", "basin", "sub", "sb"):
            if normalized.startswith(prefix):
                remainder = normalized[len(prefix):]
                if remainder:
                    return remainder
        return normalized

    @classmethod
    def _subbasin_aliases(cls, value):
        key = cls._normalize_subbasin_name(value)
        aliases = {key}
        if not key:
            return aliases

        digits_only = "".join(ch for ch in key if ch.isdigit())
        if digits_only:
            aliases.add(digits_only)

        if key.startswith("subbasin"):
            aliases.add(key[len("subbasin"):])
        if key.startswith("basin"):
            aliases.add(key[len("basin"):])
        if key.startswith("sub") and len(key) > 3:
            aliases.add(key[3:])
        return {alias for alias in aliases if alias}

    @classmethod
    def _resolve_zonal_mean(cls, zonal_lookup, subbasin_value):
        if subbasin_value is None:
            return None

        direct_key = cls._normalize_subbasin_name(subbasin_value)
        if direct_key in zonal_lookup:
            return zonal_lookup[direct_key]

        for alias in cls._subbasin_aliases(subbasin_value):
            if alias in zonal_lookup:
                return zonal_lookup[alias]

        digits_only = "".join(ch for ch in direct_key if ch.isdigit())
        if digits_only:
            for candidate_key, value in zonal_lookup.items():
                candidate_digits = "".join(ch for ch in candidate_key if ch.isdigit())
                if candidate_digits == digits_only:
                    return value

        direct_key_len = len(direct_key)
        for candidate_key, value in zonal_lookup.items():
            if candidate_key == direct_key:
                return value
            if direct_key and candidate_key and (candidate_key.endswith(direct_key) or direct_key.endswith(candidate_key)):
                return value
            if direct_key and candidate_key and (direct_key in candidate_key or candidate_key in direct_key):
                return value
            if (
                direct_key
                and candidate_key
                and abs(len(candidate_key) - direct_key_len) <= 2
                and candidate_key.replace(digits_only, "") == direct_key.replace(digits_only, "")
            ):
                return value

        return None

    def _load_zonal_statistics(self):
        zonal_path = self.zonal_file_var.get().strip()
        if not zonal_path:
            raise ValueError("Select a Zonal Statistics CSV file first.")

        zonal_df = read_table(zonal_path)
        if zonal_df.empty:
            raise ValueError("The selected zonal statistics file is empty.")

        if "MEAN" not in zonal_df.columns and "mean" not in zonal_df.columns:
            raise ValueError("Zonal statistics file must contain a MEAN column.")
        mean_col = "MEAN" if "MEAN" in zonal_df.columns else "mean"

        name_col = None
        for candidate in zonal_df.columns:
            normalized = candidate.strip().lower()
            if "sub" in normalized and "basin" in normalized:
                name_col = candidate
                break
        if name_col is None:
            for candidate in zonal_df.columns:
                normalized = candidate.strip().lower()
                if "basin" in normalized:
                    name_col = candidate
                    break
        if name_col is None:
            raise ValueError("Zonal statistics file must include a sub-basin name column.")

        lookup = {}
        for _, row in zonal_df.iterrows():
            name = row.get(name_col)
            if pd.isna(name) or str(name).strip() == "":
                continue
            mean_value = pd.to_numeric(row.get(mean_col), errors="coerce")
            if pd.isna(mean_value):
                continue

            normalized_name = self._normalize_subbasin_name(name)
            if not normalized_name:
                continue

            lookup[normalized_name] = float(mean_value)
            for alias in self._subbasin_aliases(name):
                if alias:
                    lookup[alias] = float(mean_value)

        if not lookup:
            raise ValueError("No valid sub-basin MEAN values were found in the zonal statistics file.")
        return lookup

    def _iter_basin_rows(self):
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
            zonal_lookup = self._load_zonal_statistics()

            row_metrics = []
            handoff_frames = []
            missing_subbasins = []
            for dam_name, basin, subbasin, year, area_km2, slope in basin_rows:
                extracted_mean = self._resolve_zonal_mean(zonal_lookup, subbasin)
                if extracted_mean is None:
                    missing_subbasins.append(str(subbasin))
                    continue
                metrics = self.app.yield_calc.calculate_metrics(
                    raster_mean_t_ha_yr=extracted_mean,
                    area_km2=area_km2,
                    slope=slope,
                )
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
                handoff_frames.append(self.app.yield_calc.to_phase2_handoff(year, metrics["volume_m3"]))

            if missing_subbasins:
                unique_missing = sorted(set(missing_subbasins))
                keys = ", ".join(sorted(zonal_lookup.keys())[:25])
                raise ValueError(
                    "MEAN value missing for sub-basin(s): "
                    f"{', '.join(unique_missing)}. Available zonal keys: {keys}"
                )

            self.app.rusle_row_metrics = row_metrics
            self.app.rusle_results_df = pd.DataFrame(row_metrics)
            self.app.rusle_metrics = row_metrics[0] if row_metrics else None
            self.app.phase2_df = (
                pd.concat(handoff_frames, ignore_index=True)
                .groupby("Year", as_index=False)["Suspended_Volume_m3"]
                .sum()
            )
            self.btn_export_phase2.config(state="normal")
            self._write_rusle_results()
        except Exception as exc:
            messagebox.showerror("RUSLE Error", str(exc))

    def _write_rusle_results(self):
        try:
            if self.app.rusle_results_df is None or self.app.rusle_results_df.empty:
                return

            for child in self.results_tree.get_children():
                self.results_tree.delete(child)

            display_cols = [
                "dam",
                "basin",
                "subbasin",
                "year",
                "usda_scs_sio",
                "cem_sio",
                "avg_sio",
                "yield_mass_t",
                "volume_m3",
                "specific_yield_m3_km2",
            ]

            for _, row in self.app.rusle_results_df.iterrows():
                values = []
                for col in display_cols:
                    val = row[col]
                    if col == "year":
                        values.append(int(val))
                    elif col in ("usda_scs_sio", "cem_sio", "avg_sio"):
                        values.append(f"{float(val):.4f}")
                    elif col == "yield_mass_t":
                        values.append(f"{float(val):.2f}")
                    elif col in ("volume_m3", "specific_yield_m3_km2"):
                        values.append(f"{float(val):.2f}")
                    else:
                        values.append(str(val))
                self.results_tree.insert("", "end", values=tuple(values))

            export_dir = Path("exports")
            export_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = export_dir / f"rusle_results_{timestamp}.csv"

            export_df = self.app.rusle_results_df[
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
            export_df.to_csv(csv_path, index=False)
        except Exception as exc:
            print(f"Error writing RUSLE results: {exc}")

    def export_yield_results_csv(self):
        if self.app.rusle_results_df is None or self.app.rusle_results_df.empty:
            messagebox.showerror("Export Error", "Run Classify & Compute Yield first.")
            return
        save_path = filedialog.asksaveasfilename(
            title="Save Yield Results CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if save_path:
            export_df = self.app.rusle_results_df[
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
