import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, List, Optional, Sequence, Tuple


def browse_open_file(
    filetypes: Sequence[Tuple[str, str]] = (
        ("CSV/Excel Files", "*.csv *.xlsx *.xls"),
        ("All Files", "*.*"),
    ),
    title: str = "Select File",
) -> Optional[str]:
    """Open a file dialog to pick an existing file."""
    path = filedialog.askopenfilename(title=title, filetypes=list(filetypes))
    return path if path else None


def browse_open_files(
    filetypes: Sequence[Tuple[str, str]] = (
        ("CSV/Excel Files", "*.csv *.xlsx *.xls"),
        ("All Files", "*.*"),
    ),
    title: str = "Select Files",
) -> List[str]:
    """Open a file dialog to pick several existing files; an empty list means the dialog was cancelled."""
    return list(filedialog.askopenfilenames(title=title, filetypes=list(filetypes)))


def browse_save_file(
    defaultextension: str = ".csv",
    filetypes: Sequence[Tuple[str, str]] = (("CSV Files", "*.csv"), ("All Files", "*.*")),
    title: str = "Save File",
) -> Optional[str]:
    """Open a file dialog to specify a save file location."""
    path = filedialog.asksaveasfilename(
        title=title,
        defaultextension=defaultextension,
        filetypes=list(filetypes),
    )
    return path if path else None


def browse_directory(title: str = "Select Folder") -> Optional[str]:
    """Open a folder dialog; the folder may be created in the dialog."""
    path = filedialog.askdirectory(title=title, mustexist=False)
    return path if path else None


def show_error(title: str, message: str) -> None:
    """Display an error messagebox."""
    messagebox.showerror(title, message)


def show_warning(title: str, message: str) -> None:
    """Display a warning messagebox."""
    messagebox.showwarning(title, message)


def show_info(title: str, message: str) -> None:
    """Display an info messagebox."""
    messagebox.showinfo(title, message)


def run_in_background(
    root: tk.Tk,
    task_fn: Callable[[], any],
    on_complete: Callable[[Optional[any], Optional[Exception]], None],
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
            error = exc
        root.after(0, lambda: on_complete(result, error))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
