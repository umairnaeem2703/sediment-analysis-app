import tkinter as tk

import pytest


@pytest.fixture(scope="session")
def tk_root():
    # One Tk interpreter per session: repeatedly creating tk.Tk() intermittently
    # fails with "Can't find a usable tk.tcl" on Windows. Tests build their UI
    # in a tk.Toplevel(tk_root) instead.
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()
