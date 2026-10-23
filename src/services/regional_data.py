"""The project's regional inputs as the wizard works with them: import, edit, validate, and keep the dams in step.

A basin table that has invalid cells is still imported and shown in a grid so it can be fixed in place; a table
that is unreadable or lacks required columns is refused and nothing is copied. Every import copies the file into
the project; the file the user picked is only read.
"""

import os
from pathlib import Path
from typing import List, NamedTuple, Optional

import pandas as pd

from src.services.project import Dam, Project, slugify
from src.services.regional import (
    DAM,
    Problem,
    TableError,
    load_dam_sheet,
    load_zonal_means,
    name_key,
    read_basin_grid,
    validate_basin_table,
)

BASIN_COPY = "inputs/basins.csv"


class SheetImport(NamedTuple):
    imported: List[str]  # names of the dams that got a sheet
    warnings: List[str]
    errors: List[str]  # one message per file that was refused


class RegionalData:
    def __init__(self, project: Project):
        self.project = project
        self.grid: Optional[pd.DataFrame] = None  # canonical columns, cell text as the user edits it
        self.problems: List[Problem] = []
        self.basin_table: Optional[pd.DataFrame] = None  # validated and numeric; None while the grid has problems
        self.zonal: Optional[pd.DataFrame] = None
        self.zonal_warnings: List[str] = []
        self.load_errors: List[str] = []
        self._load()

    @property
    def complete(self) -> bool:
        return self.basin_table is not None and self.zonal is not None

    # --- reopening ----------------------------------------------------------------------------

    def _load(self) -> None:
        """Restore the state from the copies in the project folder; a missing or broken copy is reported."""
        basins = self.project.inputs.get("basins")
        if basins:
            try:
                self.grid = read_basin_grid(self.project.folder / basins)
            except (ValueError, OSError) as exc:
                self.load_errors.append(str(exc))
            else:
                self._validate()
        zonal = self.project.inputs.get("zonal_means")
        if zonal:
            try:
                loaded = load_zonal_means(self.project.folder / zonal)
            except (ValueError, OSError) as exc:
                self.load_errors.append(str(exc))
            else:
                self.zonal, self.zonal_warnings = loaded.data, loaded.warnings

    # --- basin table --------------------------------------------------------------------------

    def import_basin_table(self, path) -> List[str]:
        """Copy a basin table into the project and validate it. Returns notices about dams that were removed."""
        grid = read_basin_grid(path)  # refuses unreadable files and missing columns before anything is copied
        self._replace_basin_copy(self.project.import_file(path, f"inputs/basins{Path(path).suffix.lower()}"))
        self.grid = grid
        return self._validate_and_sync()

    def edit_cell(self, position: int, column: str, value: str) -> List[str]:
        """Change one grid cell (position is the 0-based grid row), rewrite the project's copy and re-validate."""
        if self.grid is None:
            raise ValueError("There is no basin table to edit; import one first.")
        if column not in self.grid.columns:
            raise ValueError(f"The basin table has no column '{column}'.")
        if not 0 <= position < len(self.grid):
            raise ValueError(f"The basin table has no row {position} (it has {len(self.grid)} rows).")
        updated = self.grid.copy()
        updated.at[position, column] = str(value).strip()
        # Write first: if the file cannot be replaced (for example it is open in Excel) the grid stays as it was.
        temp = self.project.folder / (BASIN_COPY + ".tmp")
        try:
            updated.to_csv(temp, index=False, encoding="utf-8-sig")
            os.replace(temp, self.project.folder / BASIN_COPY)
        finally:
            temp.unlink(missing_ok=True)
        self.grid = updated
        self._replace_basin_copy(BASIN_COPY)
        return self._validate_and_sync()

    def _drop_previous(self, previous: Optional[str], relative: str) -> None:
        """Delete the old copy of an input when the new one has a different name (for example .xlsx then .csv)."""
        if previous and previous != relative:
            (self.project.folder / previous).unlink(missing_ok=True)

    def _replace_basin_copy(self, relative: str) -> None:
        self._drop_previous(self.project.inputs.get("basins"), relative)
        self.project.inputs["basins"] = relative
        self.project.save()

    def _validate(self) -> None:
        source = Path(self.project.inputs["basins"]).name
        try:
            table = validate_basin_table(self.grid, source).data
        except TableError as exc:
            self.basin_table, self.problems = None, exc.problems
            return
        except ValueError as exc:  # for example: every cell was blanked
            self.basin_table, self.problems = None, [Problem(str(exc))]
            return
        self.problems = self._slug_problems()
        self.basin_table = None if self.problems else table

    def _slug_problems(self) -> List[Problem]:
        """Dam names must give distinct project identifiers, or two dams would silently merge into one."""
        problems, by_slug = [], {}
        for position, name in enumerate(self.grid[DAM]):
            if not name:  # a blank grid row: validation has already rejected a missing name in any other row
                continue
            row = position + 2
            try:
                by_slug.setdefault(slugify(name), {}).setdefault(name_key(name), []).append(row)
            except ValueError:
                message = f"row {row}: the dam name '{name}' cannot be turned into a project identifier."
                problems.append(Problem(message, ((row, DAM),)))
        for slug, spellings in by_slug.items():
            if len(spellings) > 1:
                rows = sorted(row for found in spellings.values() for row in found)
                message = f"rows {', '.join(map(str, rows))}: different dam names give the same identifier '{slug}'."
                problems.append(Problem(message, tuple((row, DAM) for row in rows)))
        return problems

    def _validate_and_sync(self) -> List[str]:
        self._validate()
        return self._sync_dams() if self.basin_table is not None else []

    def _sync_dams(self) -> List[str]:
        """One dam per dam in the table: settings of the dams that stay are kept, the others are dropped."""
        wanted = {}
        for name in self.basin_table[DAM]:
            wanted.setdefault(slugify(name), name)
        existing = {dam.slug: dam for dam in self.project.dams}
        dams = []
        for slug, name in wanted.items():
            dam = existing.get(slug) or Dam(name=name, slug=slug)
            dam.name = name
            dams.append(dam)
        removed = [dam.name for dam in self.project.dams if dam.slug not in wanted]
        self.project.dams = dams
        self.project.save()
        if not removed:
            return []
        return [f"Dam(s) removed from the project because they are no longer in the basin table: {', '.join(removed)}."]

    # --- zonal means --------------------------------------------------------------------------

    def import_zonal_means(self, path) -> List[str]:
        """Validate and copy the zonal means. Returns warnings; an unusable file raises and nothing is copied."""
        loaded = load_zonal_means(path)
        relative = self.project.import_file(path, f"inputs/zonal_means{Path(path).suffix.lower()}")
        self._drop_previous(self.project.inputs.get("zonal_means"), relative)
        self.project.inputs["zonal_means"] = relative
        self.project.save()
        self.zonal, self.zonal_warnings = loaded.data, loaded.warnings
        return loaded.warnings

    # --- dam sheets ---------------------------------------------------------------------------

    def import_dam_sheets(self, paths) -> SheetImport:
        """Match each sheet to its dam by the name inside it and copy it to inputs/dams/<slug>. Bad files are skipped."""
        if self.basin_table is None:
            raise ValueError("Import a valid basin table before the dam sheets.")
        imported, warnings, errors = [], [], []
        dams = {dam.slug: dam for dam in self.project.dams}
        for path in paths:
            try:
                loaded = load_dam_sheet(path, self.basin_table)
                dam = dams[slugify(loaded.data.name)]
                relative = self.project.import_file(path, f"inputs/dams/{dam.slug}{Path(path).suffix.lower()}")
                self._drop_previous(dam.sheet, relative)
                dam.sheet = relative
            except (ValueError, OSError) as exc:
                errors.append(str(exc))
                continue
            imported.append(dam.name)
            warnings.extend(loaded.warnings)
        self.project.save()
        return SheetImport(imported, warnings, errors)
