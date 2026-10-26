import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Optional

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from src.core.projection import EXCEEDED, HORIZON_YEARS, RATE_NAMES, YEAR, Lifespan
from src.core.wilcock import WATER_YEAR_COLUMN
from src.services.integration import (
    BEDLOAD_HM3,
    ELEVATION_M,
    SUSPENDED_HM3,
    TOTAL_HM3,
    IntegrationResult,
    compute_dam_integration,
    parse_horizon,
)
from src.services.reporting import projection_figure
from src.ui.common import show_error
from src.ui.steps.base import Step
from src.ui.steps.bedload_step import BedloadStep
from src.ui.steps.dam_step import DamStep
from src.ui.steps.reservoir_step import ReservoirStep
from src.ui.steps.suspended_step import SuspendedStep

YEAR_KEY = "year"  # the first column of the annual grid; its heading is Water year or Year, as the result says
# (result column, heading with its unit, width, number format)
ANNUAL_COLUMNS = (
    (YEAR_KEY, "Year", 90, "d"),
    (SUSPENDED_HM3, "Suspended (hm³)", 120, ".4f"),
    (BEDLOAD_HM3, "Bedload (hm³)", 120, ".4f"),
    (TOTAL_HM3, "Total (hm³)", 120, ".4f"),
    (ELEVATION_M, "Elevation (m)", 110, ".2f"),
)
PROJECTION_COLUMNS = (
    ("Year", "Year", 80, "d"),
    ("Cumulative_Mean_hm3", "Volume, mean rate (hm³)", 150, ",.2f"),
    ("Cumulative_Min_hm3", "Volume, min rate (hm³)", 150, ",.2f"),
    ("Cumulative_Max_hm3", "Volume, max rate (hm³)", 150, ",.2f"),
    ("Elevation_Mean_m", "Elevation, mean rate (m)", 160, ".2f"),
    ("Elevation_Min_m", "Elevation, min rate (m)", 160, ".2f"),
    ("Elevation_Max_m", "Elevation, max rate (m)", 160, ".2f"),
)


class IntegrationStep(Step):
    """Step 7: the annual totals and elevations of the chosen dam, the sediment accumulated to date, and its projection
    and lifespan (A5, B3.4). Everything comes from steps 3 to 6 except the number of years to project (100 by default),
    which is entered here."""

    title = "Integration and projection"

    def __init__(
        self, dam_step: DamStep, suspended_step: SuspendedStep, bedload_step: BedloadStep, reservoir_step: ReservoirStep
    ):
        super().__init__()
        self.dam_step = dam_step
        self.suspended_step = suspended_step
        self.bedload_step = bedload_step
        self.reservoir_step = reservoir_step
        self.result: Optional[IntegrationResult] = None
        self._result_years: Optional[str] = None  # the years text when the result was made
        self._canvas: Optional[FigureCanvasTkAgg] = None

    def build(self, frame):
        self.dam_var = tk.StringVar()
        self.years_var = tk.StringVar(value=str(HORIZON_YEARS))
        self.years_var.trace_add("write", lambda *_: self.wizard.refresh())  # editing it un-completes the step
        self.summary_var = tk.StringVar()
        self.lifespan_var = tk.StringVar()
        self.warning_var = tk.StringVar()
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        top = ttk.Frame(frame)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        ttk.Label(top, textvariable=self.dam_var).pack(side=tk.LEFT)
        ttk.Button(top, text="Compute", command=self.compute).pack(side=tk.RIGHT)
        ttk.Entry(top, textvariable=self.years_var, width=6).pack(side=tk.RIGHT, padx=(4, 12))
        ttk.Label(top, text="Years to project:").pack(side=tk.RIGHT)

        info = ttk.Frame(frame)
        info.grid(row=1, column=0, sticky="ew", padx=10)
        self.bold_font = tkfont.nametofont("TkDefaultFont").copy()
        self.bold_font.configure(weight="bold")
        ttk.Label(info, textvariable=self.summary_var, font=self.bold_font, wraplength=640, justify=tk.LEFT).pack(
            anchor="w"
        )
        ttk.Label(info, textvariable=self.lifespan_var, wraplength=640, justify=tk.LEFT).pack(anchor="w")

        results = ttk.Notebook(frame)
        results.grid(row=2, column=0, sticky="nsew", padx=10, pady=4)
        self.annual_tree = self._add_table(results, "Annual totals", ANNUAL_COLUMNS)
        self.projection_tree = self._add_table(results, "Projection", PROJECTION_COLUMNS)
        self.chart_frame = ttk.Frame(results)
        results.add(self.chart_frame, text="Projection chart")

        ttk.Label(frame, textvariable=self.warning_var, foreground="firebrick", wraplength=640, justify=tk.LEFT).grid(
            row=3, column=0, sticky="w", padx=10, pady=4
        )

    @staticmethod
    def _add_table(notebook: ttk.Notebook, title: str, columns) -> ttk.Treeview:
        page = ttk.Frame(notebook)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        notebook.add(page, text=title)
        tree = ttk.Treeview(page, columns=[key for key, *_ in columns], show="headings", selectmode="none")
        for key, heading, width, _ in columns:
            tree.heading(key, text=heading)
            tree.column(key, width=width, stretch=False, anchor="e")
        vertical = ttk.Scrollbar(page, orient=tk.VERTICAL, command=tree.yview)
        horizontal = ttk.Scrollbar(page, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        return tree

    # --- Step contract ------------------------------------------------------------------------

    def is_complete(self) -> bool:
        """True while a result exists and the years field still shows what it was made with."""
        return self.result is not None and self.years_var.get().strip() == self._result_years

    def on_show(self):
        dam = self.dam_step.chosen
        self.dam_var.set(f"Dam: {dam.name}" if dam else "")

    def reset(self):
        self._clear_result()

    # --- actions ------------------------------------------------------------------------------

    def compute(self) -> None:
        years_text = self.years_var.get().strip()
        try:
            result = compute_dam_integration(
                self.suspended_step.result,
                self.bedload_step.result,
                self.reservoir_step.result,
                self.dam_step.chosen,
                horizon_years=parse_horizon(years_text),
            )
        except ValueError as exc:
            show_error("Integration and projection", str(exc))
            return
        self._clear_result()
        self.result, self._result_years = result, years_text
        year_heading = "Water year" if result.year_column == WATER_YEAR_COLUMN else "Year"
        self.annual_tree.heading(YEAR_KEY, text=year_heading)
        self._fill(self.annual_tree, result.annual, ANNUAL_COLUMNS)
        self._fill(self.projection_tree, result.projection, PROJECTION_COLUMNS)
        first, last = result.commissioning_year, result.analysis_year - 1
        span = f"{first} to {last}" if last >= first else "no years"
        self.summary_var.set(
            f"Accumulation to date ({span}): {result.accumulated_hm3:,.2f} hm³, reaching {result.accumulated_elevation_m:.2f} m. "
            f"Dead volume {result.dead_vol_hm3:,.2f} hm³ (Hmin {result.h_min_m:.2f} m). Analysis year {result.analysis_year}."
        )
        self.lifespan_var.set("\n".join(self._lifespan_line(name, result) for name in RATE_NAMES))
        self.warning_var.set("\n".join(result.warnings))
        self._canvas = FigureCanvasTkAgg(projection_figure(result), master=self.chart_frame)
        self._canvas.get_tk_widget().configure(width=400, height=200)  # the canvas then follows the size of the pane
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.wizard.refresh()

    @staticmethod
    def _lifespan_line(name: str, result: IntegrationResult) -> str:
        lifespan: Lifespan = result.lifespans[name]
        start = f"Lifespan at the {name.lower()} rate ({result.rates[name]:,.2f} hm³/yr): "
        if lifespan.status == EXCEEDED:
            return start + f"the dead volume was already exceeded in {result.exceeded_year}."
        if lifespan.status == YEAR:
            return (
                start
                + f"{lifespan.year:.1f}, {lifespan.year - result.analysis_year:.1f} years after {result.analysis_year}."
            )
        return start + "not reached, because no sediment arrives at this rate."

    # --- drawing ------------------------------------------------------------------------------

    @staticmethod
    def _fill(tree: ttk.Treeview, table, grid) -> None:
        """One row for each row of the table, whose columns are those of the grid in the same order."""
        for row in table.itertuples(index=False):
            tree.insert("", "end", values=[format(value, spec) for value, (*_, spec) in zip(row, grid)])

    def _clear_result(self) -> None:
        self.result = self._result_years = None
        self.annual_tree.delete(*self.annual_tree.get_children())
        self.projection_tree.delete(*self.projection_tree.get_children())
        for variable in (self.summary_var, self.lifespan_var, self.warning_var):
            variable.set("")
        if self._canvas is not None:
            self._canvas.get_tk_widget().destroy()
            self._canvas = None
