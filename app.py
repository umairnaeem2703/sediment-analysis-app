import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from database import BasinDatabase
from wilcock_engine import FractionalModel, TimeSeriesAggregator, BedloadVisualizer
from reporter import IntegrationModule

class SedimentApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Automated Sediment Analysis Software")
        self.root.geometry("950x650")
        
        self.db = BasinDatabase()
        self.load_startup_data()
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=10)
        
        self.setup_rusle_tab()
        self.setup_wc_tab()
        self.setup_integration_tab()

    def load_startup_data(self):
        try:
            self.db.load_from_excel("TR_Basin_Subbasin_Area.xlsx")
        except Exception:
            pass

    def setup_rusle_tab(self):
        self.rusle_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.rusle_frame, text="RUSLE Spatial Engine")
        
        ttk.Label(self.rusle_frame, text="Select Basin:").grid(row=0, column=0, padx=5, pady=10, sticky="w")
        self.basin_var = tk.StringVar()
        self.basin_dropdown = ttk.Combobox(self.rusle_frame, textvariable=self.basin_var, state="readonly")
        self.basin_dropdown['values'] = list(self.db.data_dict.keys()) 
        self.basin_dropdown.grid(row=0, column=1, padx=5, pady=10)
        self.basin_dropdown.bind("<<ComboboxSelected>>", self.update_subbasins)
        
        ttk.Label(self.rusle_frame, text="Select Sub-Basin:").grid(row=1, column=0, padx=5, pady=10, sticky="w")
        self.subbasin_var = tk.StringVar()
        self.subbasin_dropdown = ttk.Combobox(self.rusle_frame, textvariable=self.subbasin_var, state="readonly")
        self.subbasin_dropdown.grid(row=1, column=1, padx=5, pady=10)
        self.subbasin_dropdown.bind("<<ComboboxSelected>>", self.display_basin_parameters)

        ttk.Label(self.rusle_frame, text="Area (km²):").grid(row=2, column=0, padx=5, pady=10, sticky="w")
        self.area_var = tk.StringVar()
        ttk.Entry(self.rusle_frame, textvariable=self.area_var, state="readonly").grid(row=2, column=1, padx=5)

        ttk.Label(self.rusle_frame, text="Slope (Manual/Auto):").grid(row=3, column=0, padx=5, pady=10, sticky="w")
        self.slope_var = tk.StringVar()
        ttk.Entry(self.rusle_frame, textvariable=self.slope_var).grid(row=3, column=1, padx=5)
        
        self.btn_export_tif = ttk.Button(self.rusle_frame, text="Export Color-Coded .tif")
        self.btn_export_tif.grid(row=4, column=0, columnspan=2, pady=20)

    def update_subbasins(self, event=None):
        selected_basin = self.basin_var.get()
        if selected_basin in self.db.data_dict:
            self.subbasin_dropdown['values'] = list(self.db.data_dict[selected_basin].keys())
            self.subbasin_dropdown.set('') 
            self.area_var.set('')
            self.slope_var.set('')

    def display_basin_parameters(self, event=None):
        basin = self.basin_var.get()
        subbasin = self.subbasin_var.get()
        area, slope = self.db.get_area_and_slope(basin, subbasin)
        if area is not None:
            self.area_var.set(str(area))
            self.slope_var.set(str(slope) if slope else "")

    def setup_wc_tab(self):
        self.wc_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.wc_frame, text="Wilcock & Crowe Bedload")
        
        self.flow_file_var = tk.StringVar()
        self.frac_file_var = tk.StringVar()
        
        ttk.Button(self.wc_frame, text="Browse Daily Flow CSV", command=lambda: self.browse_file(self.flow_file_var)).grid(row=0, column=0, padx=10, pady=10, sticky="w")
        ttk.Entry(self.wc_frame, textvariable=self.flow_file_var, width=50, state="readonly").grid(row=0, column=1, padx=10, pady=10)
        
        ttk.Button(self.wc_frame, text="Browse Fractional CSV", command=lambda: self.browse_file(self.frac_file_var)).grid(row=1, column=0, padx=10, pady=10, sticky="w")
        ttk.Entry(self.wc_frame, textvariable=self.frac_file_var, width=50, state="readonly").grid(row=1, column=1, padx=10, pady=10)
        
        self.btn_export_png = ttk.Button(self.wc_frame, text="Execute & Export Trend Graph", command=self.execute_wc_analysis)
        self.btn_export_png.grid(row=2, column=0, columnspan=2, pady=20)

    def setup_integration_tab(self):
        self.integration_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.integration_frame, text="Integration & Handoff")
        
        self.phase2_file_var = tk.StringVar()
        self.phase3_file_var = tk.StringVar()
        self.bathy_file_var = tk.StringVar()
        
        ttk.Button(self.integration_frame, text="Browse Phase 2 Output (CSV)", command=lambda: self.browse_file(self.phase2_file_var)).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        ttk.Entry(self.integration_frame, textvariable=self.phase2_file_var, width=50, state="readonly").grid(row=0, column=1, padx=10, pady=5)
        
        ttk.Button(self.integration_frame, text="Browse Phase 3 Output (CSV)", command=lambda: self.browse_file(self.phase3_file_var)).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        ttk.Entry(self.integration_frame, textvariable=self.phase3_file_var, width=50, state="readonly").grid(row=1, column=1, padx=10, pady=5)
        
        ttk.Button(self.integration_frame, text="Browse Bathymetry (Optional)", command=lambda: self.browse_file(self.bathy_file_var)).grid(row=2, column=0, padx=10, pady=5, sticky="w")
        ttk.Entry(self.integration_frame, textvariable=self.bathy_file_var, width=50, state="readonly").grid(row=2, column=1, padx=10, pady=5)
        
        self.btn_run_integration = ttk.Button(self.integration_frame, text="Merge Data & Find Extremes", command=self.execute_integration)
        self.btn_run_integration.grid(row=3, column=0, columnspan=2, pady=10)
        
        self.results_text = tk.Text(self.integration_frame, height=8, width=70, state="disabled")
        self.results_text.grid(row=4, column=0, columnspan=2, padx=10, pady=5)
        
        self.btn_export_master = ttk.Button(self.integration_frame, text="Export Master Dataset (Excel)", command=self.export_master_dataset, state="disabled")
        self.btn_export_master.grid(row=5, column=0, columnspan=2, pady=10)
        
        self.final_merged_df = None

    def browse_file(self, string_var):
        filepath = filedialog.askopenfilename(filetypes=[("CSV/Excel Files", "*.csv *.xlsx"), ("All Files", "*.*")])
        if filepath:
            string_var.set(filepath)

    def execute_wc_analysis(self):
        flow_path = self.flow_file_var.get()
        frac_path = self.frac_file_var.get()

        if not flow_path or not frac_path:
            messagebox.showerror("Input Error", "Please browse and select both the Flow and Fractional Data files.")
            return

        try:
            df_flow = pd.read_csv(flow_path) if flow_path.endswith('.csv') else pd.read_excel(flow_path)
            df_frac = pd.read_csv(frac_path) if frac_path.endswith('.csv') else pd.read_excel(frac_path)

            model = FractionalModel()
            model.load_fractional_parameters(df_frac)
            
            aggregator = TimeSeriesAggregator(model)
            annual_summary = aggregator.process_annual_averages(df_flow)

            visualizer = BedloadVisualizer()
            fig = visualizer.generate_trend_graph(annual_summary)

            self.display_plot_window(fig)

        except Exception as e:
            messagebox.showerror("Analysis Error", f"An error occurred during calculation:\n\n{str(e)}")

    def display_plot_window(self, fig):
        plot_window = tk.Toplevel(self.root)
        plot_window.title("Wilcock & Crowe Bedload Trend")
        plot_window.geometry("800x600")

        canvas = FigureCanvasTkAgg(fig, master=plot_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        def save_fig():
            save_path = filedialog.asksaveasfilename(title="Save Trend Graph", defaultextension=".png", filetypes=[("PNG Image", "*.png")])
            if save_path:
                fig.savefig(save_path, dpi=300, bbox_inches='tight')
                messagebox.showinfo("Success", f"Graph successfully saved to:\n{save_path}")

        ttk.Button(plot_window, text="Export as PNG", command=save_fig).pack(pady=10)

    def execute_integration(self):
        p2_path = self.phase2_file_var.get()
        p3_path = self.phase3_file_var.get()
        bathy_path = self.bathy_file_var.get()

        if not p2_path or not p3_path:
            messagebox.showerror("Input Error", "Phase 2 and Phase 3 datasets are required.")
            return

        try:
            df_p2 = pd.read_csv(p2_path) if p2_path.endswith('.csv') else pd.read_excel(p2_path)
            df_p3 = pd.read_csv(p3_path) if p3_path.endswith('.csv') else pd.read_excel(p3_path)
            df_bathy = None
            if bathy_path:
                df_bathy = pd.read_csv(bathy_path) if bathy_path.endswith('.csv') else pd.read_excel(bathy_path)

            integration = IntegrationModule()
            self.final_merged_df = integration.merge_sediment_data(df_p2, df_p3)
            min_record, max_record = integration.locate_extremes(self.final_merged_df)
            
            if df_bathy is not None:
                min_record, max_record = integration.generate_final_report_metrics(min_record, max_record, df_bathy)

            self.results_text.config(state="normal")
            self.results_text.delete(1.0, tk.END)
            
            report = f"--- Minimum Volume Year: {min_record['Year']} ---\nTotal Volume: {min_record['Total_Volume_m3']:,.2f} m³\n"
            if 'Interpolated_Elevation_m' in min_record:
                report += f"Reservoir Elevation: {min_record['Interpolated_Elevation_m']} m\n"
            
            report += f"\n--- Maximum Volume Year: {max_record['Year']} ---\nTotal Volume: {max_record['Total_Volume_m3']:,.2f} m³\n"
            if 'Interpolated_Elevation_m' in max_record:
                report += f"Reservoir Elevation: {max_record['Interpolated_Elevation_m']} m\n"

            self.results_text.insert(tk.END, report)
            self.results_text.config(state="disabled")
            self.btn_export_master.config(state="normal")

        except Exception as e:
            messagebox.showerror("Integration Error", f"Failed to merge datasets:\n\n{str(e)}")

    def export_master_dataset(self):
        if self.final_merged_df is None or self.final_merged_df.empty:
            return
        save_path = filedialog.asksaveasfilename(title="Save Master Dataset", defaultextension=".xlsx", filetypes=[("Excel Files", "*.xlsx")])
        if save_path:
            try:
                self.final_merged_df.to_excel(save_path, index=False)
                messagebox.showinfo("Success", f"Master Dataset saved to:\n{save_path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to save file:\n\n{str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = SedimentApp(root)
    root.mainloop()