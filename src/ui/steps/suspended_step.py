import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Optional

from src.services.regional import SUBBASIN
from src.services.suspended import SuspendedResult, compute_suspended
from src.ui.common import bold_font, show_error
from src.ui.steps.base import Step
from src.ui.steps.dam_step import DamStep

# (result column, heading with its unit, width, number format)
GRID_COLUMNS = (
    (SUBBASIN, "Sub-basin", 170, ""),
    ("Area_km2", "Area (km²)", 80, "g"),
    ("Slope_m_per_m", "Slope (m/m)", 80, "g"),
    ("Zonal_Mean_t_ha_yr", "Zonal mean (t/ha/yr)", 130, ".4f"),
    ("Gross_Mass_t", "Gross erosion (t/yr)", 130, ",.0f"),
    ("SIO_USDA_SCS", "SIO USDA-SCS", 100, ".4f"),
    ("SIO_CEM", "SIO ÇEM", 90, ".4f"),
    ("SIO_Average", "SIO average", 90, ".4f"),
    ("Yield_Mass_t", "Yield (t/yr)", 100, ",.0f"),
    ("Volume_m3", "Volume (m³/yr)", 110, ",.0f"),
    ("Specific_Yield_m3_km2", "Specific yield (m³/yr/km²)", 170, ",.1f"),
)


class SuspendedStep(Step):
    """Step 4: the suspended sediment of the chosen dam (A5, B3.1). Compute runs off the Tk thread."""

    title = "Suspended sediment"

    def __init__(self, dam_step: DamStep):
        super().__init__()
        self.dam_step = dam_step
        self.result: Optional[SuspendedResult] = None

    def build(self, frame):
        self.dam_var = tk.StringVar()
        self.total_var = tk.StringVar()
        self.warning_var = tk.StringVar()
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        top = ttk.Frame(frame)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        ttk.Label(top, textvariable=self.dam_var).pack(side=tk.LEFT)
        ttk.Button(top, text="Compute", command=self.compute).pack(side=tk.RIGHT)

        grid = ttk.Frame(frame)
        grid.grid(row=1, column=0, sticky="nsew", padx=10)
        grid.columnconfigure(0, weight=1)
        grid.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(grid, columns=[key for key, *_ in GRID_COLUMNS], show="headings", selectmode="none")
        for key, heading, width, _ in GRID_COLUMNS:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, stretch=False, anchor="w" if key == SUBBASIN else "e")
        scroll = ttk.Scrollbar(grid, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(xscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=1, column=0, sticky="ew")

        self.total_font = bold_font()
        ttk.Label(frame, textvariable=self.total_var, font=self.total_font).grid(
            row=2, column=0, sticky="w", padx=10, pady=(8, 0)
        )
        ttk.Label(frame, textvariable=self.warning_var, foreground="firebrick", wraplength=620, justify=tk.LEFT).grid(
            row=3, column=0, sticky="w", padx=10, pady=4
        )

    # --- Step contract ------------------------------------------------------------------------

    def is_complete(self) -> bool:
        return self.result is not None

    def on_show(self):
        dam = self.dam_step.chosen
        self.dam_var.set(f"Dam: {dam.name}" if dam else "")

    def reset(self):
        self.result = None
        self.tree.delete(*self.tree.get_children())
        self.total_var.set("")
        self.warning_var.set("")

    # --- actions ------------------------------------------------------------------------------

    def compute(self) -> None:
        dam, project = self.dam_step.chosen, self.wizard.project
        sub_basins, zonal = self.wizard.regional.sub_basins(dam), self.wizard.regional.zonal
        source = Path(project.inputs["zonal_means"]).name  # the project's copy is what the error should name
        self.wizard.run_task(
            lambda: compute_suspended(sub_basins, zonal, source), self._computed, "Computing suspended sediment..."
        )

    def _computed(self, result: Optional[SuspendedResult], error: Optional[Exception]) -> None:
        if error is not None:
            show_error("Suspended sediment", str(error))
            return
        self.result = result
        self.tree.delete(*self.tree.get_children())
        for _, row in result.table.iterrows():
            self.tree.insert("", "end", values=[format(row[key], spec) for key, _, _, spec in GRID_COLUMNS])
        count = len(result.table)
        self.total_var.set(
            f"Dam total: {result.total_volume_m3:,.0f} m³/yr of suspended sediment from {count} sub-basin(s)."
        )
        self.warning_var.set("\n".join(result.warnings))
        self.wizard.refresh()
