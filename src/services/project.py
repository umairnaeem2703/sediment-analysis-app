"""Project model: a folder holding project.json, a copy of every imported input, and the run outputs."""

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from src.core.monthly_flow_preprocessor import DEFAULT_PHI, DEFAULT_SEED, DEFAULT_SIGMA
from src.core.rusle import to_ascii_turkish
from src.utils.log import get_logger

SCHEMA_VERSION = 1
PROJECT_FILE = "project.json"
INPUT_KEYS = ("basins", "zonal_means", "fractions")


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
class CurveOverrides:
    """The curve inputs the user changed from the dam sheet in step 6; None keeps the sheet's value."""

    bed_elev_m: Optional[float] = None
    crest_elev_m: Optional[float] = None
    max_elev_m: Optional[float] = None
    active_vol_hm3: Optional[float] = None
    max_vol_hm3: Optional[float] = None


@dataclass
class Dam:
    name: str
    slug: str
    sheet: Optional[str] = None
    flow: Flow = field(default_factory=Flow)
    curve: CurveOverrides = field(default_factory=CurveOverrides)
    commissioning_year: Optional[int] = None
    analysis_year: Optional[int] = None
    h_min_m: Optional[float] = None
    shape_class: Optional[str] = None
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
            dams = [
                Dam(**{**d, "flow": Flow(**d.get("flow", {})), "curve": CurveOverrides(**d.get("curve", {}))})
                for d in data.get("dams", [])
            ]
            inputs = {**dict.fromkeys(INPUT_KEYS), **data.get("inputs", {})}
        except TypeError as exc:
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
