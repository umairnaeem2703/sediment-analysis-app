import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk
from typing import Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from src.core.wilcock import WATER_YEAR_COLUMN
from src.services.bedload import (
    FLOW_M3_S,
    MASS_T,
    QB_M2_S,
    VOLUME_M3,
    BedloadResult,
    apply_flow_settings,
    compute_dam_bedload,
    import_flow,
    import_fractions,
)
from src.services.reporting import bedload_trend_figure
from src.ui.common import browse_open_file, show_error, show_warning
from src.ui.steps.base import Step
from src.ui.steps.dam_step import DamStep

YEAR = "year"  # the first column of the grid; its heading is Water year or Year, as the result says
# (result column, heading with its unit, width, number format)
GRID_COLUMNS = (
    (YEAR, "Year", 90, "d"),
    (FLOW_M3_S, "Mean flow (m³/s)", 120, ".3f"),
    (QB_M2_S, "Mean transport (m²/s)", 150, ".3e"),
    (VOLUME_M3, "Volume (m³/yr)", 120, ",.0f"),
    (MASS_T, "Mass (t/yr)", 110, ",.0f"),
)


class BedloadStep(Step):
    """Step 5: the bedload of the chosen dam from its flow file and the grain fractions (A5, B3.2).

    The flow is a daily series or a DSİ monthly table; a monthly table is split into synthetic daily flow with the
    entered sigma, lag-1 phi and seed and the result is flagged. Compute runs off the Tk thread.
    """

    title = "Bedload"

    def __init__(self, dam_step: DamStep):
        super().__init__()
        self.dam_step = dam_step
        self.result: Optional[BedloadResult] = None
        self._result_entries: Optional[Tuple[str, str, str]] = (
            None  # sigma, seed and phi as entered when the result was made
        )
        self._fields_slug: Optional[str] = None  # the dam whose stored sigma, seed and phi the fields were loaded from
        self._canvas: Optional[FigureCanvasTkAgg] = None

    def build(self, frame):
        self.dam_var = tk.StringVar()
        self.flow_var = tk.StringVar()
        self.fractions_var = tk.StringVar()
        self.sigma_var = tk.StringVar()
        self.seed_var = tk.StringVar()
        self.phi_var = tk.StringVar()
        self.flag_var = tk.StringVar()
        self.summary_var = tk.StringVar()
        self.warning_var = tk.StringVar()
        for variable in (self.sigma_var, self.seed_var, self.phi_var):
            variable.trace_add("write", lambda *_: self.wizard.refresh())  # editing the fields un-completes the step
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        inputs = ttk.LabelFrame(frame, text="Inputs")
        inputs.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        inputs.columnconfigure(1, weight=1)
        ttk.Label(inputs, textvariable=self.dam_var).grid(row=0, column=0, columnspan=3, sticky="w", padx=6, pady=3)
        ttk.Button(inputs, text="Flow file...", command=self.on_choose_flow).grid(row=1, column=0, padx=6, pady=3)
        ttk.Label(inputs, textvariable=self.flow_var).grid(row=1, column=1, columnspan=2, sticky="w")
        split = ttk.Frame(inputs)
        split.grid(row=2, column=1, columnspan=2, sticky="w")
        ttk.Label(split, text="DSİ monthly table: split into days with sigma").pack(side=tk.LEFT)
        ttk.Entry(split, textvariable=self.sigma_var, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(split, text="lag-1 phi").pack(side=tk.LEFT)
        ttk.Entry(split, textvariable=self.phi_var, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(split, text="and seed").pack(side=tk.LEFT)
        ttk.Entry(split, textvariable=self.seed_var, width=8).pack(side=tk.LEFT, padx=4)
        ttk.Button(inputs, text="Grain fractions...", command=self.on_choose_fractions).grid(
            row=3, column=0, padx=6, pady=3
        )
        ttk.Label(inputs, textvariable=self.fractions_var).grid(row=3, column=1, columnspan=2, sticky="w")
        ttk.Button(inputs, text="Compute", command=self.compute).grid(row=4, column=0, padx=6, pady=6)

        info = ttk.Frame(frame)
        info.grid(row=1, column=0, sticky="ew", padx=10)
        self.bold_font = tkfont.nametofont("TkDefaultFont").copy()
        self.bold_font.configure(weight="bold")
        ttk.Label(info, textvariable=self.flag_var, foreground="darkorange4", wraplength=640, justify=tk.LEFT).pack(
            anchor="w"
        )
        ttk.Label(info, textvariable=self.summary_var, font=self.bold_font).pack(anchor="w")

        results = ttk.Notebook(frame)
        results.grid(row=2, column=0, sticky="nsew", padx=10, pady=4)
        table = ttk.Frame(results)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        results.add(table, text="Annual table")
        self.tree = ttk.Treeview(table, columns=[key for key, *_ in GRID_COLUMNS], show="headings", selectmode="none")
        for key, heading, width, _ in GRID_COLUMNS:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, stretch=False, anchor="e")
        vertical = ttk.Scrollbar(table, orient=tk.VERTICAL, command=self.tree.yview)
        horizontal = ttk.Scrollbar(table, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.chart_frame = ttk.Frame(results)
        results.add(self.chart_frame, text="Trend chart")

        ttk.Label(frame, textvariable=self.warning_var, foreground="firebrick", wraplength=640, justify=tk.LEFT).grid(
            row=3, column=0, sticky="w", padx=10, pady=4
        )

    # --- Step contract ------------------------------------------------------------------------

    def _entries(self) -> Tuple[str, str, str]:
        return self.sigma_var.get().strip(), self.seed_var.get().strip(), self.phi_var.get().strip()

    def is_complete(self) -> bool:
        """True while a result exists and the sigma, seed and phi fields still show what it was made with."""
        return self.result is not None and self._entries() == self._result_entries

    def on_show(self):
        dam = self.dam_step.chosen
        self._render_inputs(reload_fields=dam is not None and dam.slug != self._fields_slug)

    def reset(self):
        self._clear_result()
        self._fields_slug = None
        if self.wizard.project is not None:
            self._render_inputs(reload_fields=False)

    # --- actions ------------------------------------------------------------------------------

    def on_choose_flow(self):
        path = browse_open_file(title="Select the flow file (a daily series or a DSİ monthly table)")
        if path:
            self.use_flow_file(path)

    def on_choose_fractions(self):
        path = browse_open_file(title="Select the grain fractions")
        if path:
            self.use_fractions_file(path)

    def use_flow_file(self, path: str) -> None:
        dam, project = self.dam_step.chosen, self.wizard.project
        try:  # the typed sigma, seed and phi are applied when computing; a daily series does not use them
            import_flow(project, dam, path, dam.flow.sigma, dam.flow.seed, dam.flow.phi)
        except (ValueError, OSError) as exc:
            show_error("Flow file", str(exc))
            return
        self._changed("The flow file was replaced.")

    def use_fractions_file(self, path: str) -> None:
        try:
            loaded = import_fractions(self.wizard.project, path)
        except (ValueError, OSError) as exc:
            show_error("Grain fractions", str(exc))
            return
        self._changed("The grain fractions were replaced.")
        if loaded.warnings:
            show_warning("Grain fractions", "\n".join(loaded.warnings))

    def compute(self) -> None:
        if self.wizard.busy:  # run_task would ignore the request, so do not store the settings or reset anything
            return
        dam, project = self.dam_step.chosen, self.wizard.project
        try:
            changed = apply_flow_settings(project, dam, self.sigma_var.get(), self.seed_var.get(), self.phi_var.get())
        except (ValueError, OSError) as exc:
            show_error("Flow settings", str(exc))
            return
        if changed:
            self.wizard.invalidate_after(self.index, "The flow settings changed.")
        entries = self._entries()  # what the result is made with, even if the fields are edited while it runs
        self.wizard.run_task(
            lambda: compute_dam_bedload(project, dam),
            lambda result, error: self._computed(result, error, entries),
            "Computing bedload...",
        )

    def _computed(
        self, result: Optional[BedloadResult], error: Optional[Exception], entries: Tuple[str, str, str]
    ) -> None:
        if error is not None:
            show_error("Bedload", str(error))
            if self.result is not None:  # the inputs changed and the old result no longer matches them
                self._clear_result()
                self.wizard.invalidate_after(self.index, "The bedload could not be recomputed.")
            self.wizard.refresh()
            return
        self._clear_result()
        self.result = result
        self._result_entries = entries
        year_heading = "Water year" if result.year_column == WATER_YEAR_COLUMN else "Year"
        self.tree.heading(YEAR, text=year_heading)
        for _, row in result.table.iterrows():
            cells = [format(int(row[result.year_column]), "d")]
            cells += [format(row[key], spec) for key, _, _, spec in GRID_COLUMNS[1:]]
            self.tree.insert("", "end", values=cells)
        count = len(result.table)
        self.summary_var.set(
            f"Mean bedload: {result.mean_volume_m3_yr:,.0f} m³/yr over {count} {year_heading.lower()}(s)."
        )
        if result.synthetic:
            self.flag_var.set("⚠ Synthetic daily flow. " + " ".join(result.notes))
        self.warning_var.set("\n".join(result.warnings))
        self._canvas = FigureCanvasTkAgg(bedload_trend_figure(result.table), master=self.chart_frame)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.wizard.refresh()

    def _changed(self, reason: str) -> None:
        """An input was replaced: the result and the later steps no longer apply."""
        self._clear_result()
        self.wizard.invalidate_after(self.index, reason)
        self._render_inputs(reload_fields=False)
        self.wizard.refresh()

    # --- drawing ------------------------------------------------------------------------------

    def _clear_result(self) -> None:
        self.result = self._result_entries = None
        self.tree.delete(*self.tree.get_children())
        for variable in (self.flag_var, self.summary_var, self.warning_var):
            variable.set("")
        if self._canvas is not None:
            self._canvas.get_tk_widget().destroy()
            self._canvas = None

    def _render_inputs(self, reload_fields: bool) -> None:
        dam = self.dam_step.chosen
        fractions = self.wizard.project.inputs.get("fractions") if self.wizard.project is not None else None
        self.dam_var.set(f"Dam: {dam.name}" if dam else "")
        flow = Path(dam.flow.path).name if dam and dam.flow.path else "none chosen"
        self.flow_var.set(f"Flow file: {flow}")
        self.fractions_var.set(f"Grain fractions: {Path(fractions).name if fractions else 'none chosen'}")
        if dam is not None and reload_fields:
            self.sigma_var.set(f"{dam.flow.sigma:g}")
            self.seed_var.set(str(dam.flow.seed))
            self.phi_var.set(f"{dam.flow.phi:g}")
            self._fields_slug = dam.slug
