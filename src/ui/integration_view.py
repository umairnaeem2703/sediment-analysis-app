import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.data.reporter import IntegrationModule
from src.utils.paths import read_table


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

        self.results_text = tk.Text(self.frame, height=10, width=70, state="disabled")
        self.results_text.grid(row=4, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")
        self.frame.rowconfigure(4, weight=1)

        self.btn_export_master = ttk.Button(
            self.frame,
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
            self.app.final_merged_df, join_warning = integration.merge_sediment_data(df_p2, df_p3)
            min_record, max_record = integration.locate_extremes(self.app.final_merged_df)

            interp_warnings = []
            if df_bathy is not None:
                min_record, max_record, interp_warnings = integration.generate_final_report_metrics(
                    min_record, max_record, df_bathy
                )

            self.results_text.config(state="normal")
            self.results_text.delete(1.0, tk.END)

            report = (
                f"--- Minimum Volume Year: {min_record['Year']} ---\n"
                f"Total Volume: {min_record['Total_Volume_m3']:,.2f} m³\n"
            )
            if "Interpolated_Elevation_m" in min_record:
                report += f"Reservoir Elevation: {min_record['Interpolated_Elevation_m']} m\n"
            report += (
                f"\n--- Maximum Volume Year: {max_record['Year']} ---\n"
                f"Total Volume: {max_record['Total_Volume_m3']:,.2f} m³\n"
            )
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
        if self.app.final_merged_df is None or self.app.final_merged_df.empty:
            return
        save_path = filedialog.asksaveasfilename(
            title="Save Master Dataset", defaultextension=".xlsx", filetypes=[("Excel Files", "*.xlsx")]
        )
        if save_path:
            try:
                self.app.final_merged_df.to_excel(save_path, index=False)
                messagebox.showinfo("Success", f"Master Dataset saved to:\n{save_path}")
            except Exception as exc:
                messagebox.showerror("Export Error", f"Failed to save file:\n\n{exc}")
