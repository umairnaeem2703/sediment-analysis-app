import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Optional

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from src.core.reservoir import AREA_KM2, ELEVATION_M, VOLUME_HM3
from src.services.dam_run import CURVE
from src.services.reporting import reservoir_curve_figure
from src.services.reservoir import CurveResult, apply_h_min, import_curve_sheet
from src.ui.common import (
    add_point_readout,
    add_table,
    bold_font,
    browse_open_file,
    format_number,
    curve_lines,
    show_error,
    show_warning,
)
from src.ui.steps.base import Step
from src.ui.steps.dam_step import DamStep

# (result column, heading with its unit, width, number format)
GRID_COLUMNS = (
    (ELEVATION_M, "Elevation (m)", 110, ".2f"),
    (VOLUME_HM3, "Volume (hm³)", 120, ".3f"),
    (AREA_KM2, "Surface area (km²)", 140, ".3f"),
)


class ReservoirStep(Step):
    """Step 6: the measured reservoir curve of the chosen dam (A5, B3.3, D75, D76).

    The user imports the dam's curve sheet and enters Hmin, the minimum operating level. Generate checks the curve and
    that Hmin lies inside it, naming every problem, keeps Hmin on the dam and shows the curve with Vdead = V(Hmin).
    """

    title = "Reservoir curve"
    stage = CURVE

    def __init__(self, dam_step: DamStep):
        super().__init__()
        self.dam_step = dam_step
        self._canvas: Optional[FigureCanvasTkAgg] = None
        self._result_h_min: Optional[str] = None  # the Hmin text when the result was made

    def build(self, frame):
        self.dam_var = tk.StringVar()
        self.curve_file_var = tk.StringVar()
        self.h_min_var = tk.StringVar()
        self.h_min_var.trace_add("write", lambda *_: self.wizard.refresh())  # editing it un-completes the step
        self.summary_var = tk.StringVar()
        self.warning_var = tk.StringVar()
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        inputs = ttk.LabelFrame(frame, text="Inputs")
        inputs.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        ttk.Label(inputs, textvariable=self.dam_var).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=3)
        ttk.Button(inputs, text="Curve sheet...", command=self.on_choose_curve).grid(row=1, column=0, padx=6, pady=3)
        ttk.Label(inputs, textvariable=self.curve_file_var).grid(row=1, column=1, sticky="w")
        ttk.Label(inputs, text="Hmin, minimum operating level (m):").grid(row=2, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(inputs, textvariable=self.h_min_var, width=14).grid(row=2, column=1, sticky="w")
        ttk.Button(inputs, text="Generate curve", command=self.generate).grid(row=3, column=0, padx=6, pady=6)

        self.bold_font = bold_font()
        ttk.Label(frame, textvariable=self.summary_var, font=self.bold_font, wraplength=640, justify=tk.LEFT).grid(
            row=1, column=0, sticky="w", padx=10
        )

        results = ttk.Notebook(frame)
        results.grid(row=2, column=0, sticky="nsew", padx=10, pady=4)
        self.tree = add_table(results, "Curve table", GRID_COLUMNS)
        self.chart_frame = ttk.Frame(results)
        results.add(self.chart_frame, text="Curve chart")

        ttk.Label(frame, textvariable=self.warning_var, foreground="firebrick", wraplength=640, justify=tk.LEFT).grid(
            row=3, column=0, sticky="w", padx=10, pady=4
        )

    # --- Step contract ------------------------------------------------------------------------

    def is_complete(self) -> bool:
        """True while a result exists and the Hmin field still shows what it was made with."""
        return self.result is not None and self.h_min_var.get().strip() == self._result_h_min

    def on_show(self):
        self._render_inputs()
        dam = self.dam_step.chosen
        if dam is not None and dam.h_min_m is not None and not self.h_min_var.get().strip():
            self.h_min_var.set(format_number(dam.h_min_m))  # keep what the user has typed

    def reset(self):
        self._clear_result()
        dam = self.dam_step.chosen if self.wizard.project is not None else None
        self.h_min_var.set("" if dam is None or dam.h_min_m is None else format_number(dam.h_min_m))
        if self.wizard.project is not None:
            self._render_inputs()

    # --- actions ------------------------------------------------------------------------------

    def on_choose_curve(self):
        path = browse_open_file(title="Select the reservoir curve sheet")
        if path:
            self.use_curve_file(path)

    def use_curve_file(self, path: str) -> None:
        try:
            loaded = import_curve_sheet(self.wizard.project, self.dam_step.chosen, path)
        except (ValueError, OSError) as exc:
            show_error("Curve sheet", str(exc))
            return
        self._clear_result()
        self.wizard.invalidate_after(self.index, "The curve sheet was replaced.")
        self._render_inputs()
        self.wizard.refresh()
        if loaded.warnings:
            show_warning("Curve sheet", "\n".join(loaded.warnings))

    def generate(self) -> None:
        dam, text = self.dam_step.chosen, self.h_min_var.get().strip()
        before = dam.h_min_m
        try:
            result = apply_h_min(self.wizard.project, dam, text)
        except (ValueError, OSError) as exc:
            show_error("Reservoir curve", str(exc))
            return
        if dam.h_min_m != before:
            self.wizard.invalidate_after(self.index, "Hmin changed.")
        self._show_result(result)
        self._result_h_min = text
        self.wizard.refresh()

    def _show_result(self, result: CurveResult) -> None:
        self._clear_result()
        self.result = result
        curve = result.curve
        self.summary_var.set(
            f"Dead volume {curve.dead_vol_hm3:.2f} hm³ below Hmin {curve.h_min_m:.2f} m. "
            f"Hbed {curve.bed_elev_m:g} m, Hcrest {curve.crest_elev_m:g} m, Vmax {curve.max_vol_hm3:.2f} hm³."
        )
        for _, row in result.table.iterrows():
            self.tree.insert("", "end", values=[format(row[key], spec) for key, _, _, spec in GRID_COLUMNS])
        self.warning_var.set("\n".join(result.warnings))
        self._canvas = FigureCanvasTkAgg(reservoir_curve_figure(result), master=self.chart_frame)
        self._canvas.get_tk_widget().configure(width=400, height=200)  # the canvas then follows the size of the pane
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        add_point_readout(self._canvas, lines=curve_lines(self._canvas.figure))
        self.wizard.refresh()

    # --- drawing ------------------------------------------------------------------------------

    def _clear_result(self) -> None:
        self.result = None
        self._result_h_min = None
        self.tree.delete(*self.tree.get_children())
        for variable in (self.summary_var, self.warning_var):
            variable.set("")
        if self._canvas is not None:
            self._canvas.get_tk_widget().destroy()
            self._canvas = None

    def _render_inputs(self) -> None:
        dam = self.dam_step.chosen
        self.dam_var.set(f"Dam: {dam.name}" if dam else "")
        name = Path(dam.curve_sheet).name if dam and dam.curve_sheet else "none chosen"
        self.curve_file_var.set(f"Curve sheet: {name}")
