import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from src.core.reservoir import AREA_KM2, ELEVATION_M, SHAPE_CLASSES, STEP_M, VOLUME_HM3
from src.services.reporting import reservoir_curve_figure
from src.services.reservoir import (
    FIELDS,
    CurveResult,
    apply_curve_settings,
    compute_curve,
    curve_inputs,
    parse_table_step,
    sheet_differences,
)
from src.ui.common import format_number, show_error
from src.ui.steps.base import Step
from src.ui.steps.dam_step import DamStep

# (result column, heading with its unit, width, number format)
GRID_COLUMNS = (
    (ELEVATION_M, "Elevation (m)", 110, ".1f"),
    (VOLUME_HM3, "Volume (hm³)", 120, ".3f"),
    (AREA_KM2, "Surface area (km²)", 140, ".3f"),
)


class ReservoirStep(Step):
    """Step 6: confirm or edit the inputs of the chosen dam's reservoir curve and generate it (A5, B3.3).

    The inputs are prefilled from the dam sheet. Hmin is the dam's own setting from step 3, and the shape class fixes
    the curve when Hmin is blank. An input that differs from the sheet is kept on the dam and listed. The level interval
    of the table (0.5 m by default) only sets the table and its chart; it is not kept on the dam.
    """

    title = "Reservoir curve"

    def __init__(self, dam_step: DamStep):
        super().__init__()
        self.dam_step = dam_step
        self.result: Optional[CurveResult] = None
        self._result_entries: Optional[Tuple[str, ...]] = None  # the field texts when the result was made
        self._fields_slug: Optional[str] = None  # the dam whose stored inputs the fields were loaded from
        self._canvas: Optional[FigureCanvasTkAgg] = None

    def build(self, frame):
        self.dam_var = tk.StringVar()
        self.bed_var = tk.StringVar()
        self.h_min_var = tk.StringVar()
        self.max_elev_var = tk.StringVar()
        self.crest_var = tk.StringVar()
        self.active_var = tk.StringVar()
        self.max_vol_var = tk.StringVar()
        self.shape_var = tk.StringVar()
        self.step_var = tk.StringVar(value=format_number(STEP_M))
        self.edits_var = tk.StringVar()
        self.summary_var = tk.StringVar()
        self.warning_var = tk.StringVar()
        self._input_vars = dict(
            zip(
                FIELDS,
                (self.bed_var, self.h_min_var, self.max_elev_var, self.crest_var, self.active_var, self.max_vol_var),
            )
        )
        for variable in (*self._input_vars.values(), self.shape_var, self.step_var):
            variable.trace_add("write", lambda *_: self.wizard.refresh())  # editing the fields un-completes the step
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        inputs = ttk.LabelFrame(frame, text="Curve inputs")
        inputs.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        ttk.Label(inputs, textvariable=self.dam_var).grid(row=0, column=0, columnspan=4, sticky="w", padx=6, pady=3)
        for position, (name, (words, symbol, unit)) in enumerate(FIELDS.items()):  # three to a column
            row, column = 1 + position % 3, 2 * (position // 3)
            optional = " (optional)" if name == "h_min_m" else ""
            ttk.Label(inputs, text=f"{words} {symbol} ({unit}){optional}:").grid(
                row=row, column=column, sticky="w", padx=6
            )
            ttk.Entry(inputs, textvariable=self._input_vars[name], width=12).grid(
                row=row, column=column + 1, sticky="w", pady=2
            )
        ttk.Label(inputs, text="Shape class (fixes the curve when Hmin is blank):").grid(
            row=4, column=0, sticky="w", padx=6
        )
        self.shape_box = ttk.Combobox(
            inputs, textvariable=self.shape_var, values=list(SHAPE_CLASSES), state="readonly", width=10
        )
        self.shape_box.grid(row=4, column=1, sticky="w", pady=2)
        ttk.Label(inputs, text="Level interval of the table (m):").grid(row=4, column=2, sticky="w", padx=6)
        ttk.Entry(inputs, textvariable=self.step_var, width=12).grid(row=4, column=3, sticky="w", pady=2)
        ttk.Button(inputs, text="Generate curve", command=self.generate).grid(
            row=5, column=0, columnspan=2, sticky="w", padx=6, pady=6
        )

        info = ttk.Frame(frame)
        info.grid(row=1, column=0, sticky="ew", padx=10)
        self.bold_font = tkfont.nametofont("TkDefaultFont").copy()
        self.bold_font.configure(weight="bold")
        ttk.Label(info, textvariable=self.edits_var, foreground="darkorange4", wraplength=640, justify=tk.LEFT).pack(
            anchor="w"
        )
        ttk.Label(info, textvariable=self.summary_var, font=self.bold_font, wraplength=640, justify=tk.LEFT).pack(
            anchor="w"
        )

        results = ttk.Notebook(frame)
        results.grid(row=2, column=0, sticky="nsew", padx=10, pady=4)
        table = ttk.Frame(results)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        results.add(table, text="Curve table")
        self.tree = ttk.Treeview(table, columns=[key for key, *_ in GRID_COLUMNS], show="headings", selectmode="none")
        for key, heading, width, _ in GRID_COLUMNS:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, stretch=False, anchor="e")
        vertical = ttk.Scrollbar(table, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vertical.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        self.chart_frame = ttk.Frame(results)
        results.add(self.chart_frame, text="Curve chart")

        ttk.Label(frame, textvariable=self.warning_var, foreground="firebrick", wraplength=640, justify=tk.LEFT).grid(
            row=3, column=0, sticky="w", padx=10, pady=4
        )

    # --- Step contract ------------------------------------------------------------------------

    def _entries(self) -> Tuple[str, ...]:
        """The texts of the curve inputs, the shape class and the level interval, in that order."""
        return tuple(variable.get().strip() for variable in (*self._input_vars.values(), self.shape_var, self.step_var))

    def is_complete(self) -> bool:
        """True while a curve exists and the fields still show what it was made with."""
        return self.result is not None and self._entries() == self._result_entries

    def on_show(self):
        dam = self.dam_step.chosen
        self.dam_var.set(f"Dam: {dam.name}" if dam else "")
        if dam is not None and dam.slug != self._fields_slug:
            self._load_fields(dam)

    def reset(self):
        self._clear_result()
        self._fields_slug = None

    # --- actions ------------------------------------------------------------------------------

    def generate(self) -> None:
        dam, project = self.dam_step.chosen, self.wizard.project
        *curve_texts, step_text = self._entries()
        try:
            sheet = self.wizard.regional.dam_sheet(dam).data
            step_m = parse_table_step(step_text)  # refused before anything is kept on the dam
            changed = apply_curve_settings(project, dam, sheet, **dict(zip((*FIELDS, "shape_class"), curve_texts)))
            result = compute_curve(curve_inputs(sheet, dam), sheet.drainage_area_km2, step_m)
        except (ValueError, OSError) as exc:
            show_error("Reservoir curve", str(exc))
            return
        self.dam_step.set_h_min(dam.h_min_m)
        if changed:
            self.wizard.invalidate_after(self.index, "The reservoir curve changed.")
        self._load_fields(dam, sheet)  # show the values as stored
        self._show_result(result)

    def _show_result(self, result: CurveResult) -> None:
        self._clear_result()
        self.result = result
        self._result_entries = self._entries()
        curve = result.curve
        source = "given" if result.h_min_given else f"from the {result.shape_class} shape class"
        self.summary_var.set(
            f"Exponent m = {curve.exponent:.2f}. Hmin {curve.h_min_m:.2f} m ({source}). "
            f"Dead volume {curve.dead_vol_hm3:.2f} hm³. Surface area at Hmax {curve.area(curve.max_elev_m):.2f} km²."
        )
        for _, row in result.table.iterrows():
            self.tree.insert("", "end", values=[format(row[key], spec) for key, _, _, spec in GRID_COLUMNS])
        self.warning_var.set("\n".join(result.warnings))
        self._canvas = FigureCanvasTkAgg(reservoir_curve_figure(result), master=self.chart_frame)
        self._canvas.get_tk_widget().configure(width=400, height=200)  # the canvas then follows the size of the pane
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.wizard.refresh()

    # --- drawing ------------------------------------------------------------------------------

    def _clear_result(self) -> None:
        self.result = self._result_entries = None
        self.tree.delete(*self.tree.get_children())
        for variable in (self.summary_var, self.warning_var):
            variable.set("")
        if self._canvas is not None:
            self._canvas.get_tk_widget().destroy()
            self._canvas = None

    def _load_fields(self, dam, sheet=None) -> None:
        """Fill the fields with the dam's stored inputs: the sheet's values, the dam's edits, Hmin and the shape class."""
        if sheet is None:
            try:
                sheet = self.wizard.regional.dam_sheet(dam).data
            except (ValueError, OSError) as exc:
                for variable in (*self._input_vars.values(), self.shape_var):
                    variable.set("")  # not the previous dam's values
                self.edits_var.set(f"The dam sheet of {dam.name} cannot be read: {exc}")
                return
        inputs = curve_inputs(sheet, dam)
        for name, variable in self._input_vars.items():
            value = getattr(inputs, name)
            variable.set("" if value is None else format_number(value))
        self.shape_var.set(inputs.shape_class or "")
        differences = sheet_differences(sheet, inputs)
        self.edits_var.set("Changed from the dam sheet: " + "; ".join(differences) + "." if differences else "")
        self._fields_slug = dam.slug
