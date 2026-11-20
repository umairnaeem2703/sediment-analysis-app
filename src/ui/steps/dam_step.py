import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple

from src.services.dam_run import DamRun
from src.services.dam_settings import apply_dam_settings
from src.services.project import Dam
from src.services.regional import AREA, SLOPE, SUBBASIN
from src.ui.common import format_number, show_error
from src.ui.steps.base import Step


class DamStep(Step):
    """Step 3: pick the dam to analyse and enter its settings (A5)."""

    title = "Select dam"

    def build(self, frame):
        self._selected_slug: Optional[str] = None
        self.confirmed: Optional[str] = None  # slug of the dam the user has chosen with "Use this dam"
        self._confirmed_entries: Optional[Tuple[str, ...]] = None  # the field texts at that moment
        self.info_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.commissioning_var = tk.StringVar()
        self.analysis_var = tk.StringVar()
        self.efficiency_var = tk.StringVar(value="100")
        for variable in (self.commissioning_var, self.analysis_var, self.efficiency_var):
            variable.trace_add("write", lambda *_: self.wizard.refresh())  # editing the fields un-confirms the dam
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(frame, text="Dams")
        left.grid(row=0, column=0, sticky="ns", padx=(10, 5), pady=8)
        self.dam_list = tk.Listbox(left, width=24, height=14, exportselection=False, activestyle="none")
        self.dam_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.dam_list.bind("<<ListboxSelect>>", self._on_list_select)

        right = ttk.Frame(frame)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=8)
        right.columnconfigure(0, weight=1)

        basins = ttk.LabelFrame(right, text="Sub-basins")
        basins.grid(row=0, column=0, sticky="ew")
        columns = (SUBBASIN, AREA, SLOPE)
        self.sub_basin_tree = ttk.Treeview(basins, columns=columns, show="headings", height=4, selectmode="none")
        for column in columns:
            self.sub_basin_tree.heading(column, text=column)
            self.sub_basin_tree.column(column, width=170, anchor="w")
        self.sub_basin_tree.pack(fill=tk.X, padx=6, pady=6)

        ttk.Label(right, textvariable=self.info_var, justify=tk.LEFT).grid(row=1, column=0, sticky="w", pady=6)

        settings = ttk.LabelFrame(right, text="Settings")
        settings.grid(row=2, column=0, sticky="ew")
        fields = (
            ("Commissioning year (optional):", self.commissioning_var),
            ("Analysis year (blank = current year):", self.analysis_var),
            ("Trap efficiency (%):", self.efficiency_var),
        )
        for row, (label, variable) in enumerate(fields):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=3)
            ttk.Entry(settings, textvariable=variable, width=14).grid(row=row, column=1, sticky="w", padx=6)
        ttk.Button(settings, text="Use this dam", command=self.use_dam).grid(row=len(fields), column=0, padx=6, pady=6)
        ttk.Label(right, textvariable=self.status_var).grid(row=3, column=0, sticky="w", pady=4)

    # --- Step contract ------------------------------------------------------------------------

    @property
    def selected(self) -> Optional[Dam]:
        """The dam shown, looked up by slug so it stays current when the dams are re-synced."""
        return self._dam(self._selected_slug)

    @property
    def chosen(self) -> Optional[Dam]:
        """The dam confirmed with "Use this dam"; the later steps analyse this one."""
        return self._dam(self.confirmed)

    def _dam(self, slug: Optional[str]) -> Optional[Dam]:
        return next((dam for dam in self.wizard.project.dams if dam.slug == slug), None) if slug else None

    def _entries(self) -> Tuple[str, ...]:
        variables = (self.commissioning_var, self.analysis_var, self.efficiency_var)
        return tuple(variable.get().strip() for variable in variables)

    def is_complete(self) -> bool:
        """True while a dam is confirmed and the fields still show what was confirmed."""
        return self._dam(self.confirmed) is not None and self._entries() == self._confirmed_entries

    def on_show(self):
        self._render_list()
        self._show_dam(reload_fields=False)  # keep what the user has typed

    def _unconfirm(self) -> None:
        """Forget the dam in use, and with it the run that holds its results."""
        self.confirmed = self._confirmed_entries = None
        self.wizard.run = None
        self.status_var.set("")

    def reset(self):
        self._unconfirm()
        if self.wizard.project is not None:
            self._render_list()
            self._show_dam(reload_fields=True)

    # --- actions ------------------------------------------------------------------------------

    def _on_list_select(self, _event=None):
        chosen = self.dam_list.curselection()
        if chosen:
            self.select_dam(self.wizard.project.dams[chosen[0]].slug)

    def select_dam(self, slug: str) -> None:
        different = slug != self._selected_slug
        self._selected_slug = slug
        if self.confirmed is not None and self.confirmed != slug:
            self.wizard.invalidate_after(self.index, "A different dam was selected.")  # before the run goes
            self._unconfirm()
        self._render_list()
        self._show_dam(reload_fields=different)  # choosing the same dam again keeps the typed text
        self.wizard.refresh()

    def use_dam(self) -> None:
        dam = self.selected
        if dam is None:
            show_error("Select a dam", "Select a dam in the list first.")
            return
        before = (dam.commissioning_year, dam.analysis_year, dam.trap_efficiency_pct)
        try:
            apply_dam_settings(
                self.wizard.project,
                dam,
                commissioning_year=self.commissioning_var.get(),
                analysis_year=self.analysis_var.get(),
                trap_efficiency_pct=self.efficiency_var.get(),
            )
        except (ValueError, OSError) as exc:
            show_error("Dam settings", str(exc))
            return
        after = (dam.commissioning_year, dam.analysis_year, dam.trap_efficiency_pct)
        changed = self.confirmed != dam.slug or before != after
        self.confirmed = dam.slug
        if changed:
            self.wizard.invalidate_after(self.index, "The dam settings changed.")
        if self.wizard.run is None or self.wizard.run.dam.slug != dam.slug:
            self.wizard.run = DamRun(dam)
        self.status_var.set(f"{dam.name} will be analysed.")
        self._show_dam(reload_fields=True)  # show the values as stored
        self._confirmed_entries = self._entries()
        self.wizard.refresh()

    # --- drawing ------------------------------------------------------------------------------

    def _render_list(self) -> None:
        if self.selected is None:
            self._selected_slug = None
        self.dam_list.delete(0, tk.END)
        for position, dam in enumerate(self.wizard.project.dams):
            self.dam_list.insert(tk.END, dam.name)
            if dam.slug == self._selected_slug:
                self.dam_list.selection_set(position)

    def _show_dam(self, reload_fields: bool) -> None:
        self.sub_basin_tree.delete(*self.sub_basin_tree.get_children())
        dam, regional = self.selected, self.wizard.regional
        if dam is None or regional is None or regional.basin_table is None:
            self.info_var.set(
                "Select a dam in the list." if dam is None else "Complete step 2 (Regional data) to see this dam."
            )
            if reload_fields:
                self._set_fields("", "", "100")
            return
        for _, row in regional.sub_basins(dam).iterrows():
            self.sub_basin_tree.insert("", "end", values=(row[SUBBASIN], row[AREA], row[SLOPE]))
        self.info_var.set("")
        if reload_fields:
            self._set_fields(
                "" if dam.commissioning_year is None else str(dam.commissioning_year),
                "" if dam.analysis_year is None else str(dam.analysis_year),
                format_number(dam.trap_efficiency_pct),
            )

    def _set_fields(self, commissioning: str, analysis: str, efficiency: str) -> None:
        self.commissioning_var.set(commissioning)
        self.analysis_var.set(analysis)
        self.efficiency_var.set(efficiency)
