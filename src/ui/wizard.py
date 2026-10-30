"""The main window: a step list on the left, the current step beside it, Back and Next at the bottom (A5)."""

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Sequence

from src.services.project import Project
from src.services.regional_data import RegionalData
from src.ui.common import EXPECTED_ERRORS, install_error_handler, run_in_background, unexpected_message
from src.ui.steps.base import Step
from src.ui.steps.bedload_step import BedloadStep
from src.ui.steps.dam_step import DamStep
from src.ui.steps.integration_step import IntegrationStep
from src.ui.steps.project_step import ProjectStep
from src.ui.steps.regional_step import RegionalStep
from src.ui.steps.report_step import ReportStep
from src.ui.steps.reservoir_step import ReservoirStep
from src.ui.steps.suspended_step import SuspendedStep
from src.utils.log import attach_project_log, configure, get_logger


class Wizard:
    """Owns navigation, gating and invalidation. Steps own their own widgets and results."""

    def __init__(self, parent: tk.Misc, steps: Sequence[Step]):
        self.parent = parent
        self.steps: List[Step] = list(steps)
        self.project: Optional[Project] = None
        self.regional: Optional[RegionalData] = None
        self.current = 0
        self.busy = False
        self.notice_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.frame = ttk.Frame(parent)
        self._build()
        self.go_to(0)

    def _build(self) -> None:
        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(0, weight=1)

        self.step_list = ttk.Treeview(self.frame, show="tree", selectmode="browse", height=max(len(self.steps), 1))
        self.step_list.column("#0", width=210, stretch=False)
        self.step_list.tag_configure("done", foreground="dark green")
        self.step_list.tag_configure("locked", foreground="gray55")
        for index, step in enumerate(self.steps):
            self.step_list.insert("", "end", iid=str(index), text=step.title)
        self.step_list.grid(row=0, column=0, sticky="ns", padx=(10, 5), pady=10)
        self.step_list.bind("<<TreeviewSelect>>", self._on_select)

        content = ttk.Frame(self.frame)
        content.grid(row=0, column=1, sticky="nsew", padx=5, pady=10)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        for step in self.steps:
            step.attach(self, content)

        bottom = ttk.Frame(self.frame)
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.notice_var, wraplength=620, foreground="firebrick").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(bottom, textvariable=self.status_var).grid(row=1, column=0, sticky="w")
        self.back_button = ttk.Button(bottom, text="< Back", command=self.back)
        self.back_button.grid(row=0, column=1, rowspan=2, padx=4)
        self.next_button = ttk.Button(bottom, text="Next >", command=self.next)
        self.next_button.grid(row=0, column=2, rowspan=2)

    # --- navigation ---------------------------------------------------------------------------

    def can_enter(self, index: int) -> bool:
        """A step opens only when every step before it is complete."""
        return 0 <= index < len(self.steps) and all(step.is_complete() for step in self.steps[:index])

    def go_to(self, index: int) -> bool:
        if self.busy or not self.can_enter(index):
            return False
        self._show(index)
        return True

    def _show(self, index: int) -> None:
        """Make `index` the visible step. Only its frame is laid out, so hidden steps take no keyboard focus."""
        self.current = index
        self.notice_var.set("")
        for position, step in enumerate(self.steps):
            if position == index:
                step.frame.grid(row=0, column=0, sticky="nsew")
            else:
                step.frame.grid_remove()
        self.steps[index].on_show()
        self.refresh()

    def next(self) -> None:
        if self.steps[self.current].is_complete():
            self.go_to(self.current + 1)

    def back(self) -> None:
        self.go_to(self.current - 1)

    def _on_select(self, _event=None) -> None:
        selected = self.step_list.selection()
        if selected and int(selected[0]) != self.current and not self.go_to(int(selected[0])):
            self._sync_selection()  # the clicked step is locked: put the highlight back

    def _sync_selection(self) -> None:
        # selection_set always fires <<TreeviewSelect>>, so only touch the selection when it differs.
        if tuple(self.step_list.selection()) != (str(self.current),):
            self.step_list.selection_set(str(self.current))

    # --- state --------------------------------------------------------------------------------

    def set_project(self, project: Project) -> None:
        if self.project == project:  # re-opening the same project keeps the open one and its later results
            self.refresh()
            return
        self.project = project
        self.regional = RegionalData(project)
        attach_project_log(project.folder)
        get_logger().info("Project %s opened from %s.", project.name, project.folder)
        self.invalidate_after(0, "The project changed.")

    def add_notice(self, text: str) -> None:
        self.notice_var.set(f"{self.notice_var.get()} {text}".strip())

    def invalidate_after(self, index: int, reason: str) -> None:
        """An earlier step changed: clear every later step and say which results were lost (FR-X-04)."""
        later = self.steps[index + 1 :]
        lost = [step.title for step in later if step.is_complete()]
        for step in later:
            step.reset()
        if self.current > index:
            self._show(index)  # not go_to: the user must leave a reset step even while a task is running
        self.notice_var.set(f"{reason} Reset: {', '.join(lost)}." if lost else "")
        self.refresh()

    def refresh(self) -> None:
        """Re-draw the step list and the Back/Next buttons from the steps' current state."""
        for index, step in enumerate(self.steps):
            if step.is_complete():
                mark, tags = "✓", ("done",)
            elif not self.can_enter(index):
                mark, tags = "-", ("locked",)
            else:
                mark, tags = " ", ()
            self.step_list.item(str(index), text=f"{mark} {index + 1}. {step.title}", tags=tags)
        self._sync_selection()
        idle = not self.busy
        back_ok = idle and self.current > 0
        next_ok = idle and self.current < len(self.steps) - 1 and self.steps[self.current].is_complete()
        self.back_button.state(["!disabled" if back_ok else "disabled"])
        self.next_button.state(["!disabled" if next_ok else "disabled"])

    # --- background work ----------------------------------------------------------------------

    def run_task(self, task: Callable, on_done: Callable, status: str = "Working...") -> None:
        """Run `task` off the Tk thread (FR-X-05); navigation is disabled until `on_done(result, error)` runs."""
        if self.busy:
            return
        self.busy = True
        self.status_var.set(status)
        self.refresh()
        get_logger().info(status)

        def finished(result, error):
            self.busy = False
            self.status_var.set("")
            self.refresh()
            if error is not None and not isinstance(error, EXPECTED_ERRORS):
                error = RuntimeError(unexpected_message(error))  # already logged with its traceback
            on_done(result, error)

        run_in_background(self.parent, task, finished)


def default_steps() -> List[Step]:
    dam_step = DamStep()
    suspended, bedload, reservoir = SuspendedStep(dam_step), BedloadStep(dam_step), ReservoirStep(dam_step)
    integration = IntegrationStep(dam_step, suspended, bedload, reservoir)
    return [
        ProjectStep(),
        RegionalStep(),
        dam_step,
        suspended,
        bedload,
        reservoir,
        integration,
        ReportStep(dam_step, suspended, bedload, reservoir, integration),
    ]


def main() -> None:
    configure()
    root = tk.Tk()
    install_error_handler(root)
    root.title("Sediment Analysis")
    root.geometry("1000x650")
    Wizard(root, default_steps()).frame.pack(fill=tk.BOTH, expand=True)
    root.mainloop()


if __name__ == "__main__":
    main()
