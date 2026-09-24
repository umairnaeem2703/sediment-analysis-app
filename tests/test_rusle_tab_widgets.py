import tkinter as tk
from tkinter import ttk

from app import SedimentApp


def test_rusle_tab_uses_basin_grid_not_dropdowns():
    root = tk.Tk()
    try:
        app = SedimentApp(root)
        assert not hasattr(app, "basin_dropdown")
        assert not hasattr(app, "subbasin_dropdown")
        assert not hasattr(app, "area_var")
        assert not hasattr(app, "slope_var")
        assert isinstance(app.basin_tree, ttk.Treeview)
        headings = [app.basin_tree.heading(col)["text"] for col in app.basin_tree["columns"]]
        assert headings == ["Dam Name", "Basin", "Sub-Basin", "Year", "Area", "Slope"]
        labels = [w.cget("text") for w in app.rusle_frame.winfo_children() if isinstance(w, ttk.Button)]
        assert "Browse Basin File" in labels
    finally:
        root.destroy()
