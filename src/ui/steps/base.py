from tkinter import ttk


class Step:
    """One wizard step. The Wizard asks `is_complete` to gate Next and calls `reset` when an earlier step changes.

    A step that changes its own result calls `wizard.invalidate_after(index, reason)` so later steps are cleared,
    then `wizard.refresh()`.
    """

    title = ""

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
