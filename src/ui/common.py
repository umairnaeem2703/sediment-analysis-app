"""Helpers shared by the steps: file and folder dialogs, the error and warning dialogs (which also log), a scrolled
result table, `add_point_readout`, which shows the values of a chart point under the pointer, and `run_in_background`,
which runs a task off the Tk thread and logs how it failed.
"""

import logging
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Any, Callable, List, Optional, Sequence, Tuple

import numpy as np
from matplotlib.lines import Line2D
from matplotlib.transforms import IdentityTransform

from src.utils.log import get_logger, log_file

# What a service raises for a bad input or file: the message is for the user. Anything else is a fault in the program.
EXPECTED_ERRORS = (ValueError, OSError, KeyError)
TABLE_FILETYPES = (("CSV/Excel Files", "*.csv *.xlsx *.xls"), ("All Files", "*.*"))


def browse_open_file(
    filetypes: Sequence[Tuple[str, str]] = TABLE_FILETYPES, title: str = "Select File"
) -> Optional[str]:
    """Open a file dialog to pick an existing file."""
    return filedialog.askopenfilename(title=title, filetypes=list(filetypes)) or None


def browse_open_files(filetypes: Sequence[Tuple[str, str]] = TABLE_FILETYPES, title: str = "Select Files") -> List[str]:
    """Open a file dialog to pick several existing files; an empty list means the dialog was cancelled."""
    return list(filedialog.askopenfilenames(title=title, filetypes=list(filetypes)))


def browse_directory(title: str = "Select Folder") -> Optional[str]:
    """Open a folder dialog; the folder may be created in the dialog."""
    return filedialog.askdirectory(title=title, mustexist=False) or None


def format_number(value: float) -> str:
    """A stored number as text without losing digits (100.0 -> '100', 93.456789 -> '93.456789')."""
    return f"{value:.12g}"


def bold_font() -> tkfont.Font:
    """A bold copy of the default font. Keep a reference to it: Tk deletes the font when the object is collected."""
    font = tkfont.nametofont("TkDefaultFont").copy()
    font.configure(weight="bold")
    return font


def add_table(notebook: ttk.Notebook, title: str, columns) -> ttk.Treeview:
    """A notebook page holding a scrolled, right-aligned grid of `columns` (key, heading, width, number format)."""
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


def show_error(title: str, message: str) -> None:
    """Display an error messagebox, and record it in the log."""
    get_logger().warning("%s: %s", title, message)
    messagebox.showerror(title, message)


def show_warning(title: str, message: str) -> None:
    """Display a warning messagebox, and record it in the log."""
    get_logger().warning("%s: %s", title, message)
    messagebox.showwarning(title, message)


def run_in_background(
    root: tk.Tk,
    task_fn: Callable[[], Any],
    on_complete: Callable[[Optional[Any], Optional[Exception]], None],
) -> threading.Thread:
    """
    Execute a callable task in a background daemon thread and dispatch its
    result or exception back to the Tk main loop safely via root.after(0, ...).
    """

    def worker():
        result = None
        error = None
        try:
            result = task_fn()
        except Exception as exc:
            # The traceback goes to the log for every failure: a ValueError or KeyError can come from a fault in the
            # program as well as from an input, and the dialog can not show it.
            level = logging.WARNING if isinstance(exc, EXPECTED_ERRORS) else logging.ERROR
            get_logger().log(level, "A background task failed.", exc_info=exc)
            error = exc
        root.after(0, lambda: on_complete(result, error))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


def unexpected_message(error: BaseException) -> str:
    """The text of the dialog for an error the program did not foresee: the cause, and where the traceback is."""
    path = log_file()
    where = f"Details are in {path}." if path is not None else "The traceback was not saved: no project log is open."
    return f"Unexpected {type(error).__name__}: {error}\n{where}"


def install_error_handler(root: tk.Tk) -> None:
    """Log and show an error raised in a Tk callback, which Tk would otherwise print to a console nobody sees."""

    def handler(exc_type, exc, traceback):
        get_logger().error("An error in the interface.", exc_info=(exc_type, exc, traceback))
        messagebox.showerror("Unexpected error", unexpected_message(exc))  # not show_error: it is logged above

    root.report_callback_exception = handler


def add_point_readout(canvas, radius_px: float = 10) -> None:
    """Show the values of the marked points of a chart while the pointer is over one of them.

    The point nearest the pointer, within `radius_px`, is ringed together with the points of the other marked lines at
    the same x, and a note gives that x and each y with its axis label, so the values of a twin-axis chart can be read.
    """
    figure = canvas.figure
    lines = [line for axis in figure.axes for line in axis.get_lines() if line.get_marker() not in (None, "None", "")]
    x_label = lines[0].axes.get_xlabel() if lines else ""
    rings = Line2D([], [], linestyle="none", marker="o", markersize=13, markerfacecolor="none", markeredgecolor="black")
    rings.set_transform(IdentityTransform())  # display pixels, so the twin axes need no conversion
    figure.add_artist(rings)
    note = figure.axes[-1].annotate(
        "",
        xy=(0, 0),
        xycoords="figure pixels",
        xytext=(14, 14),
        textcoords="offset points",
        fontsize=9,
        bbox={"boxstyle": "round", "facecolor": "lightyellow", "edgecolor": "gray"},
        zorder=10,
    )
    rings.set_visible(False)
    note.set_visible(False)
    shown: List[Any] = [None]  # the x being shown, so the chart is redrawn only when it changes

    def show(x) -> None:
        if x == shown[0]:
            return
        shown[0] = x
        rings.set_visible(x is not None)
        note.set_visible(x is not None)
        if x is not None:
            points, text = [], [f"{x_label}: {x:g}"]
            for line in lines:
                for xy in line.get_xydata():
                    if xy[0] == x:
                        points.append(line.get_transform().transform(xy))
                        value = format(xy[1], ",.0f" if abs(xy[1]) >= 100 else ".3g")
                        text.append(f"{line.axes.get_ylabel()}: {value}")
            rings.set_data([p[0] for p in points], [p[1] for p in points])
            anchor = points[0]
            left, low = anchor[0] > figure.bbox.width * 0.65, anchor[1] > figure.bbox.height * 0.6
            note.xy = anchor
            note.set_text("\n".join(text))
            note.set_position((-14 if left else 14, -14 if low else 14))
            note.set_horizontalalignment("right" if left else "left")
            note.set_verticalalignment("top" if low else "bottom")
        canvas.draw_idle()

    def on_move(event) -> None:
        nearest, nearest_x = radius_px, None
        for line in lines:
            xy = line.get_xydata()
            if not len(xy):
                continue
            pixels = line.get_transform().transform(xy)
            distances = np.hypot(pixels[:, 0] - event.x, pixels[:, 1] - event.y)
            index = int(np.nanargmin(distances))
            if distances[index] <= nearest:
                nearest, nearest_x = distances[index], xy[index][0]
        show(nearest_x)

    canvas.mpl_connect("motion_notify_event", on_move)
    canvas.mpl_connect("figure_leave_event", lambda _event: show(None))
