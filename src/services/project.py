"""Project model: a folder holding project.json, a copy of every imported input, and the run outputs."""

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from src.core.monthly_flow_preprocessor import DEFAULT_PHI, DEFAULT_SEED, DEFAULT_SIGMA
from src.core.text import to_ascii_turkish
from src.utils.log import get_logger

SCHEMA_VERSION = 3
PROJECT_FILE = "project.json"
INPUT_KEYS = ("basins", "zonal_means", "fractions")
_GENERATED_CURVE_KEYS = ("curve", "h_min_m", "shape_class")  # what version 1 kept for the generated curve (D75)
_DAM_SHEET_KEY = "sheet"  # what versions 1 and 2 kept for the dam sheet, which the curve sheet replaces (D76)


def slugify(name: str) -> str:
    """ASCII, lowercase, underscore-separated identifier for a dam name ('Çubuk 1' -> 'cubuk_1')."""
    slug = re.sub(r"[^a-z0-9]+", "_", to_ascii_turkish(name).lower()).strip("_")
    if not slug:
        raise ValueError(f"Cannot make a slug from {name!r}.")
    return slug


@dataclass
class Flow:
    path: Optional[str] = None
    sigma: float = DEFAULT_SIGMA
    seed: int = DEFAULT_SEED
    phi: float = DEFAULT_PHI


@dataclass
class Dam:
    name: str
    slug: str
    flow: Flow = field(default_factory=Flow)
    curve_sheet: Optional[str] = None
    h_min_m: Optional[float] = None
    commissioning_year: Optional[int] = None
    analysis_year: Optional[int] = None
    trap_efficiency_pct: float = 100.0


@dataclass
class Project:
    folder: Path
    name: str
    inputs: Dict[str, Optional[str]] = field(default_factory=lambda: dict.fromkeys(INPUT_KEYS))
    dams: List[Dam] = field(default_factory=list)

    @classmethod
    def new(cls, folder, name: str) -> "Project":
        folder = Path(folder)
        if (folder / PROJECT_FILE).exists():
            raise ValueError(f"{folder} already contains a project ({PROJECT_FILE}).")
        (folder / "inputs").mkdir(parents=True, exist_ok=True)
        (folder / "outputs").mkdir(exist_ok=True)
        project = cls(folder, name)
        project.save()
        return project

    @classmethod
    def open(cls, folder) -> "Project":
        folder = Path(folder)
        path = folder / PROJECT_FILE
        if not path.is_file():
            raise ValueError(f"{path} not found: this folder is not a project.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} is not valid JSON: {exc}") from exc

        version = data.get("schema_version") if isinstance(data, dict) else None
        if not isinstance(version, int):
            raise ValueError(f"{path} has no schema_version.")
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"{path} was written by a newer version of this app "
                f"(schema_version {version}; this app supports {SCHEMA_VERSION})."
            )
        try:
            dropped = {_DAM_SHEET_KEY} if version < 3 else set()  # the curve sheet replaces the dam sheet (D76)
            if version == 1:  # the measured curve replaces the generated one: its inputs are dropped
                dropped.update(_GENERATED_CURVE_KEYS)
            data["dams"] = [
                {key: value for key, value in d.items() if key not in dropped} for d in data.get("dams", [])
            ]
            dams = [Dam(**{**d, "flow": Flow(**d.get("flow", {}))}) for d in data.get("dams", [])]
            inputs = {**dict.fromkeys(INPUT_KEYS), **data.get("inputs", {})}
        except (TypeError, AttributeError) as exc:
            raise ValueError(f"{path} is malformed ({exc}).") from exc
        return cls(folder, data.get("name", folder.name), inputs, dams)

    def save(self) -> None:
        data = {
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "inputs": self.inputs,
            "dams": [asdict(dam) for dam in self.dams],
        }
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        path = self.folder / PROJECT_FILE
        temp = path.with_name(PROJECT_FILE + ".tmp")
        temp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temp, path)

    def add_dam(self, name: str) -> Dam:
        slug = slugify(name)
        if any(dam.slug == slug for dam in self.dams):
            raise ValueError(f"A dam with slug '{slug}' already exists in this project.")
        dam = Dam(name=name, slug=slug)
        self.dams.append(dam)
        return dam

    def import_file(self, source, destination: str) -> str:
        """Copy `source` to `destination` (a path under inputs/) and return that path, POSIX-style.

        The original is only read, never modified.
        """
        relative = PurePosixPath(destination)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.parts[:1] != ("inputs",)
            or len(relative.parts) < 2
        ):
            raise ValueError(f"Import destination '{destination}' must be a relative path inside 'inputs'.")
        if not Path(source).is_file():
            raise FileNotFoundError(f"Cannot import {source}: file not found.")
        target = self.folder.joinpath(*relative.parts)
        if target.exists() and target.samefile(source):
            return relative.as_posix()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        get_logger().info("Imported %s as %s.", source, relative.as_posix())
        return relative.as_posix()
