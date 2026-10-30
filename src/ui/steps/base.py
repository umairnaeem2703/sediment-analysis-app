from tkinter import ttk
from typing import Optional


class Step:
    """One wizard step. The Wizard asks `is_complete` to gate Next and calls `reset` when an earlier step changes.

    A step that changes its own result calls `wizard.invalidate_after(index, reason)` so later steps are cleared,
    then `wizard.refresh()`.
    """

    title = ""
    stage: Optional[str] = None  # the DamRun stage whose result this step shows, for steps 4 to 7

    def __init__(self):
        self.wizard = None
        self.frame = None

    def attach(self, wizard, parent) -> None:
        self.wizard = wizard
        self.frame = ttk.Frame(parent)
        self.build(self.frame)

    def build(self, frame) -> None:
        raise NotImplementedError

    def on_show(self) -> None:
        """Called each time the step becomes the visible one."""

    def is_complete(self) -> bool:
        return False

    def reset(self) -> None:
        """Clear this step's result because an earlier step changed."""

    @property
    def index(self) -> int:
        return self.wizard.steps.index(self)

    @property
    def result(self):
        """The result of this step's stage for the dam being analysed; None while there is none."""
        run = self.wizard.run if self.wizard is not None else None
        return run.get(self.stage) if run is not None and self.stage else None

    @result.setter
    def result(self, value) -> None:
        run = self.wizard.run if self.wizard is not None else None
        if run is not None and self.stage:
            run.set(self.stage, value)
        elif value is not None:
            raise RuntimeError("A result can only be kept once a dam has been chosen.")
