import tkinter as tk
from tkinter import ttk
from typing import List

from src.services.regional import BASIN_COLUMNS
from src.ui.common import browse_open_file, browse_open_files, show_error, show_warning
from src.ui.steps.base import Step

COLUMNS = list(BASIN_COLUMNS.values())
FLAG = "⚠ "


class RegionalStep(Step):
    """Step 2: import the basin table, zonal means and dam sheets; fix invalid basin cells in a grid (FR-M1-02..06)."""

    title = "Regional data"

    def build(self, frame):
        self.status_vars = {key: tk.StringVar() for key in ("basin", "zonal", "sheets")}
        self._editor = None
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        buttons = ttk.Frame(frame)
        buttons.grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        ttk.Button(buttons, text="Import basin table...", command=self.on_import_basin).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(buttons, text="Import zonal means...", command=self.on_import_zonal).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Import dam sheets...", command=self.on_import_sheets).pack(side=tk.LEFT, padx=6)

        status = ttk.Frame(frame)
        status.grid(row=1, column=0, sticky="w", padx=10)
        for var in self.status_vars.values():
            ttk.Label(status, textvariable=var).pack(anchor="w")

        grid_frame = ttk.Frame(frame)
        grid_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=6)
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(grid_frame, columns=COLUMNS, show="headings", height=8, selectmode="browse")
        for column in COLUMNS:
            self.tree.heading(column, text=column)
            self.tree.column(column, width=150, anchor="w")
        self.tree.tag_configure("invalid", background="#fbe3e3", foreground="black")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(grid_frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", self._begin_edit)
        ttk.Label(grid_frame, text="Double-click a cell to edit it; Enter saves, Escape cancels.").grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )

        self.problem_list = tk.Listbox(frame, height=5, activestyle="none", foreground="firebrick")
        self.problem_list.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))

    # --- Step contract ------------------------------------------------------------------------

    def is_complete(self) -> bool:
        return self.wizard.regional is not None and self.wizard.regional.complete

    def on_show(self):
        self._render()

    def reset(self):
        self._end_edit()
        self._render()

    # --- actions ------------------------------------------------------------------------------

    def on_import_basin(self):
        path = browse_open_file(title="Select the basin table")
        if path:
            self.import_basin_table(path)

    def on_import_zonal(self):
        path = browse_open_file(title="Select the zonal means")
        if path:
            self.import_zonal_means(path)

    def on_import_sheets(self):
        paths = browse_open_files(title="Select the dam sheets")
        if paths:
            self.import_dam_sheets(paths)

    def import_basin_table(self, path: str) -> None:
        try:
            notices = self.wizard.regional.import_basin_table(path)
        except (ValueError, OSError) as exc:
            show_error("Basin table", str(exc))
            return
        self._changed("The basin table was replaced.", notices)

    def import_zonal_means(self, path: str) -> None:
        try:
            warnings = self.wizard.regional.import_zonal_means(path)
        except (ValueError, OSError) as exc:
            show_error("Zonal means", str(exc))
            return
        self._changed("The zonal means were replaced.", [])
        if warnings:
            show_warning("Zonal means", "\n".join(warnings))

    def import_dam_sheets(self, paths: List[str]) -> None:
        try:
            result = self.wizard.regional.import_dam_sheets(paths)
        except ValueError as exc:
            show_error("Dam sheets", str(exc))
            return
        if result.imported:
            self._changed("Dam sheets were imported.", [])
        if result.errors:
            show_error("Dam sheets", "\n".join(result.errors))
        if result.warnings:
            show_warning("Dam sheets", "\n".join(result.warnings))

    def commit_edit(self, position: int, column: str, value: str) -> None:
        """Save one edited cell. Nothing happens when the text is unchanged."""
        if value.strip() == self.wizard.regional.grid.at[position, column]:
            return
        try:
            notices = self.wizard.regional.edit_cell(position, column, value)
        except (ValueError, OSError) as exc:
            show_error("Edit cell", str(exc))
            return
        self._changed("The basin table was edited.", notices)

    def _changed(self, reason: str, notices: List[str]) -> None:
        self.wizard.invalidate_after(self.index, reason)
        for notice in notices:
            self.wizard.add_notice(notice)
        self._render()
        self.wizard.refresh()

    # --- cell editing -------------------------------------------------------------------------

    def _begin_edit(self, event):
        self._end_edit()
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        item, column_id = self.tree.identify_row(event.y), self.tree.identify_column(event.x)
        if not item:
            return
        position, column = int(item), COLUMNS[int(column_id[1:]) - 1]
        x, y, width, height = self.tree.bbox(item, column_id)
        entry = ttk.Entry(self.tree)
        entry.insert(0, self.wizard.regional.grid.at[position, column])
        entry.place(x=x, y=y, width=width, height=height)
        entry.select_range(0, tk.END)
        entry.focus_set()
        entry.bind("<Return>", lambda _event: self._finish_edit(entry, position, column))
        entry.bind("<FocusOut>", lambda _event: self._finish_edit(entry, position, column))
        entry.bind("<Escape>", lambda _event: self._end_edit())
        self._editor = entry

    def _finish_edit(self, entry, position: int, column: str) -> None:
        if self._editor is not entry:  # already finished: Return is followed by a FocusOut
            return
        value = entry.get()
        self._end_edit()
        self.commit_edit(position, column, value)

    def _end_edit(self) -> None:
        editor, self._editor = self._editor, None
        if editor is not None:
            editor.destroy()

    # --- drawing ------------------------------------------------------------------------------

    def _render(self) -> None:
        regional = self.wizard.regional
        self.tree.delete(*self.tree.get_children())
        self.problem_list.delete(0, tk.END)
        if regional is None:
            return
        flagged = {cell for problem in regional.problems for cell in problem.cells}
        if regional.grid is not None:
            for position, record in regional.grid.iterrows():
                row = position + 2  # rows count from the header = 1, as in the messages
                values = [(FLAG if (row, column) in flagged else "") + record[column] for column in COLUMNS]
                bad = any((row, column) in flagged for column in COLUMNS)
                self.tree.insert("", "end", iid=str(position), values=values, tags=("invalid",) if bad else ())
        for problem in regional.problems:
            self.problem_list.insert(tk.END, problem.message)
        for message in regional.load_errors:
            self.problem_list.insert(tk.END, f"Not loaded: {message}")
        self.status_vars["basin"].set(self._basin_status(regional))
        self.status_vars["zonal"].set(self._zonal_status(regional))
        self.status_vars["sheets"].set(self._sheet_status(regional))

    @staticmethod
    def _basin_status(regional) -> str:
        if regional.grid is None:
            return "Basin table: not imported."
        if regional.basin_table is None:
            return f"Basin table: {len(regional.problems)} problem(s). Fix the flagged cells below."
        dams = len(regional.project.dams)
        return f"Basin table: valid, {len(regional.basin_table)} sub-basin row(s), {dams} dam(s)."

    @staticmethod
    def _zonal_status(regional) -> str:
        if regional.zonal is None:
            return "Zonal means: not imported."
        return f"Zonal means: {len(regional.zonal)} sub-basin(s) loaded."

    @staticmethod
    def _sheet_status(regional) -> str:
        dams = regional.project.dams
        if regional.basin_table is None or not dams:
            return "Dam sheets: import them once the basin table is valid."
        with_sheet = sum(1 for dam in dams if dam.sheet)
        return f"Dam sheets: {with_sheet} of {len(dams)} dam(s) have a sheet (only the dam you analyse needs one)."
