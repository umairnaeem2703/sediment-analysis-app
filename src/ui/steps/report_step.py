import tkinter as tk
from tkinter import ttk
from typing import List, Optional

from src.services.run_export import RunExport, collect_warnings, export_run
from src.ui.common import bold_font, show_error
from src.ui.steps.base import Step
from src.ui.steps.dam_step import DamStep


class ReportStep(Step):
    """Step 8: the years of the minimum and maximum annual volume of the chosen dam, and the run folder written from
    the results of steps 4 to 7 (A5, FR-M5-01 to FR-M5-03). Every Export writes a new folder."""

    title = "Report"

    def __init__(self, dam_step: DamStep):
        super().__init__()
        self.dam_step = dam_step
        self.exported: Optional[RunExport] = None

    def build(self, frame):
        self.dam_var = tk.StringVar()
        self.extremes_var = tk.StringVar()
        self.folder_var = tk.StringVar()
        self.files_var = tk.StringVar()
        self.warning_var = tk.StringVar()
        frame.columnconfigure(0, weight=1)

        top = ttk.Frame(frame)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        ttk.Label(top, textvariable=self.dam_var).pack(side=tk.LEFT)
        ttk.Button(top, text="Export", command=self.export).pack(side=tk.RIGHT)

        self.bold_font = bold_font()
        ttk.Label(frame, textvariable=self.extremes_var, font=self.bold_font, justify=tk.LEFT).grid(
            row=1, column=0, sticky="w", padx=10, pady=4
        )
        ttk.Label(frame, textvariable=self.folder_var, wraplength=640, justify=tk.LEFT).grid(
            row=2, column=0, sticky="w", padx=10, pady=(8, 0)
        )
        ttk.Label(frame, textvariable=self.files_var, wraplength=640, justify=tk.LEFT).grid(
            row=3, column=0, sticky="w", padx=10
        )
        ttk.Label(frame, textvariable=self.warning_var, foreground="firebrick", wraplength=640, justify=tk.LEFT).grid(
            row=4, column=0, sticky="w", padx=10, pady=8
        )

    # --- Step contract ------------------------------------------------------------------------

    def is_complete(self) -> bool:
        return self.exported is not None

    def on_show(self):
        dam, run = self.dam_step.chosen, self.wizard.run
        integration = run.integration if run is not None else None
        self.dam_var.set(f"Dam: {dam.name}" if dam else "")
        if dam is None or integration is None:
            return
        lowest, highest = integration.extremes
        self.extremes_var.set(
            "\n".join(
                f"{label}: {extreme.year}, {extreme.total_hm3:.4f} hm³, elevation {extreme.elevation_m:.2f} m"
                for label, extreme in (("Minimum", lowest), ("Maximum", highest))
            )
        )
        warnings = collect_warnings(self._input_warnings(dam), *run.results())
        self.warning_var.set("\n".join(f"{phase}: {text}" for phase, text in warnings))

    def reset(self):
        self.exported = None
        for variable in (self.extremes_var, self.folder_var, self.files_var, self.warning_var):
            variable.set("")

    # --- actions ------------------------------------------------------------------------------

    def _input_warnings(self, dam) -> List[str]:
        """The warnings of the basin table, the zonal means and the dam sheet, which the results do not carry."""
        regional = self.wizard.regional
        try:
            return [*regional.basin_warnings, *regional.zonal_warnings, *regional.dam_sheet(dam).warnings]
        except (ValueError, OSError):  # the export names the missing file
            return []

    def export(self) -> None:
        project, run = self.wizard.project, self.wizard.run
        try:
            results = run.results()
        except ValueError as exc:
            show_error("Report", str(exc))
            return
        dam = run.dam

        def task():
            return export_run(project, dam, *results, input_warnings=self._input_warnings(dam))

        def done(result, error):
            if error is not None:
                show_error("Report", str(error))
                return
            self.exported = result
            self.folder_var.set(f"Written to {result.folder}")
            self.files_var.set("\n".join(str(path) for path in result.files))
            self.wizard.refresh()

        self.wizard.run_task(task, done, "Writing the run folder...")
