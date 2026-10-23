"""Test doubles for the wizard shell."""

from tkinter import ttk

from src.ui.steps.base import Step


class FakeStep(Step):
    def __init__(self, title):
        super().__init__()
        self.title = title
        self.done = False
        self.resets = 0
        self.shown = 0

    def build(self, frame):
        ttk.Label(frame, text=self.title).pack()

    def on_show(self):
        self.shown += 1

    def is_complete(self):
        return self.done

    def reset(self):
        self.done = False
        self.resets += 1
