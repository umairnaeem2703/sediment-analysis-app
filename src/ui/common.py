import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Any, Callable, List, Optional, Sequence, Tuple

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
    """Display a warning messagebox."""
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
        except EXPECTED_ERRORS as exc:
            error = exc
        except Exception as exc:  # a fault in the program: keep the traceback, which the dialog can not show
            get_logger().error("A background task failed.", exc_info=exc)
            error = exc
        root.after(0, lambda: on_complete(result, error))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


def unexpected_message(error: BaseException) -> str:
    """The text of the dialog for an error the program did not foresee: the cause, and where the traceback is."""
    path = log_file()
    where = f"Details are in {path}." if path is not None else "Details are in the console."
    return f"Unexpected {type(error).__name__}: {error}\n{where}"


def install_error_handler(root: tk.Tk) -> None:
    """Log and show an error raised in a Tk callback, which Tk would otherwise print to a console nobody sees."""

    def handler(exc_type, exc, traceback):
        get_logger().error("An error in the interface.", exc_info=(exc_type, exc, traceback))
        show_error("Unexpected error", unexpected_message(exc))

    root.report_callback_exception = handler
