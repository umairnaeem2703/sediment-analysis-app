import tkinter as tk
from pathlib import Path
from tkinter import ttk

from src.services.project import Project
from src.ui.common import browse_directory, show_error
from src.ui.steps.base import Step


class ProjectStep(Step):
    """Step 1: create a project folder or open an existing one."""

    title = "Project"

    def build(self, frame):
        self.name_var = tk.StringVar()
        self.folder_var = tk.StringVar()
        self.summary_var = tk.StringVar(value="No project is open.")
        frame.columnconfigure(1, weight=1)

        new = ttk.LabelFrame(frame, text="New project")
        new.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        new.columnconfigure(1, weight=1)
        ttk.Label(new, text="Project name:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(new, textvariable=self.name_var).grid(row=0, column=1, columnspan=2, sticky="ew", padx=8)
        ttk.Label(new, text="Project folder:").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(new, textvariable=self.folder_var, state="readonly").grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(new, text="Browse...", command=self.browse).grid(row=1, column=2, padx=(0, 8))
        ttk.Button(new, text="Create project", command=self.on_create).grid(row=2, column=0, sticky="w", padx=8, pady=6)

        existing = ttk.LabelFrame(frame, text="Existing project")
        existing.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        ttk.Button(existing, text="Open project...", command=self.on_open).pack(side=tk.LEFT, padx=8, pady=6)

        ttk.Label(frame, textvariable=self.summary_var).grid(row=2, column=0, sticky="w", padx=10, pady=8)

    def is_complete(self) -> bool:
        return self.wizard.project is not None

    def browse(self):
        folder = browse_directory("Select the project folder")
        if folder:
            self.folder_var.set(folder)
            if not self.name_var.get().strip():
                self.name_var.set(Path(folder).name)

    def on_create(self):
        self.create_project(self.folder_var.get(), self.name_var.get())

    def on_open(self):
        folder = browse_directory("Open a project folder")
        if folder:
            self.open_project(folder)

    def create_project(self, folder: str, name: str) -> None:
        folder, name = folder.strip(), name.strip()
        if not folder or not name:
            show_error("New project", "Choose a project folder and enter a project name.")
            return
        try:
            project = Project.new(folder, name)
        except (ValueError, OSError) as exc:
            show_error("New project", str(exc))
            return
        self._opened(project)

    def open_project(self, folder: str) -> None:
        try:
            project = Project.open(folder)
        except (ValueError, OSError) as exc:
            show_error("Open project", str(exc))
            return
        self._opened(project)

    def _opened(self, project: Project) -> None:
        self.name_var.set("")  # the form above is for the next new project, not for the open one
        self.folder_var.set("")
        self.summary_var.set(f"Open project: '{project.name}' in {project.folder} ({len(project.dams)} dam(s)).")
        self.wizard.set_project(project)
