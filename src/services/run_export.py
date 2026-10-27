"""The run folder of one dam (FR-M5-02, FR-M5-03, NFR-04, B4).

`export_run` writes `<project>/outputs/<dam-slug>_<YYYYMMDD_HHMM>/` from the results of steps 4 to 7: the workbook, the
charts, one CSV per phase and `run.json`. A run never overwrites another: a folder that exists gets `_2`, `_3`, ... The
inputs are hashed before anything is created, so a missing input leaves no folder behind, and a folder whose writing
fails is removed. `run.json` is written last.
"""

import datetime
import hashlib
import itertools
import json
import shutil
from pathlib import Path
from typing import Any, List, NamedTuple, Optional, Sequence, Tuple

import pandas as pd

from src import __version__
from src.core.projection import EXCEEDED, RATE_NAMES, YEAR
from src.services.bedload import BedloadResult, write_bedload_csv
from src.services.integration import IntegrationResult, write_integration_csv, write_projection_csv
from src.services.project import INPUT_KEYS, Dam, Project
from src.services.reporting import write_annual_volume, write_bedload_trend, write_projection, write_reservoir_curve
from src.services.reservoir import CurveResult, write_reservoir_csv
from src.services.suspended import SuspendedResult, table_with_total, write_suspended_csv

WORKBOOK = "results.xlsx"
RUN_JSON = "run.json"
STAMP_FORMAT = "%Y%m%d_%H%M"

INPUTS_SHEET, WARNINGS_SHEET, EXTREMES_SHEET = "Inputs", "Warnings", "Extremes"
INPUT_COLUMNS = ["Group", "Item", "Value", "Unit", "SHA-256"]
EXTREME_COLUMNS = ["Extreme", "Year", "Total_hm3", "Elevation_m"]
SUMMARY_COLUMNS = ["Item", "Value", "Unit"]
WARNING_COLUMNS = ["Phase", "Warning"]


class InputFile(NamedTuple):
    role: str
    path: str  # relative to the project folder
    sha256: str


class Parameter(NamedTuple):
    name: str
    value: Any
    unit: str


class RunExport(NamedTuple):
    folder: Path
    files: List[Path]


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _input_files(project: Project, dam: Dam) -> List[InputFile]:
    """Every file the run read, with its SHA-256. A missing input is an error naming it (FR-X-01)."""
    entries = [(role, project.inputs.get(role)) for role in INPUT_KEYS]
    entries += [("dam_sheet", dam.sheet), ("flow", dam.flow.path)]
    files = []
    for role, relative in entries:
        label = role.replace("_", " ")
        if not relative:
            raise ValueError(f"The project has no {label} file for {dam.name}.")
        path = project.folder / relative
        if not path.is_file():
            raise ValueError(f"The {label} file {relative} is missing from the project folder.")
        files.append(InputFile(role, relative, _sha256(path)))
    return files


def _parameters(dam: Dam, curve: CurveResult, integration: IntegrationResult) -> List[Parameter]:
    shape = curve.curve
    return [
        Parameter("Sigma", dam.flow.sigma, ""),
        Parameter("Seed", dam.flow.seed, ""),
        Parameter("Phi", dam.flow.phi, ""),
        Parameter("Trap efficiency", integration.trap_efficiency_pct, "%"),
        Parameter("Commissioning year", integration.commissioning_year, ""),
        Parameter("Analysis year", integration.analysis_year, ""),
        Parameter("Projection length", len(integration.projection) - 1, "years"),
        Parameter("Level interval", curve.step_m, "m"),
        Parameter("Hbed", shape.bed_elev_m, "m"),
        Parameter("Hmin", dam.h_min_m, "m"),  # as entered; blank when the shape class fixed the curve
        Parameter("Hmin of the curve", shape.h_min_m, "m"),
        Parameter("Hmax", shape.max_elev_m, "m"),
        Parameter("Hcrest", shape.crest_elev_m, "m"),
        Parameter("Vactive", shape.active_vol_hm3, "hm³"),
        Parameter("Vmax", shape.max_vol_hm3, "hm³"),
        Parameter("Vdead", shape.dead_vol_hm3, "hm³"),
        Parameter("Exponent m", shape.exponent, ""),
    ]


def collect_warnings(
    input_warnings: Sequence[str],
    suspended: SuspendedResult,
    bedload: BedloadResult,
    curve: CurveResult,
    integration: IntegrationResult,
) -> List[Tuple[str, str]]:
    """Every warning of the run with the phase it came from, in the order of the steps (NFR-04)."""
    phases = (
        ("Inputs", input_warnings),
        ("Suspended", suspended.warnings),
        ("Bedload", bedload.warnings),
        ("Reservoir curve", curve.warnings),
        ("Integration", integration.warnings),
    )
    return [(phase, text) for phase, texts in phases for text in texts]


def _lifespan(name: str, integration: IntegrationResult) -> Tuple[Any, str]:
    reached = integration.lifespans[name]
    if reached.status == YEAR:
        return reached.year, "year"
    if reached.status == EXCEEDED:
        year = integration.exceeded_year  # None when no year of the accumulation reached it (a dead volume of 0)
        return "Already exceeded" if year is None else f"Already exceeded in {year}", ""
    return "Not reached", ""


def _summary(integration: IntegrationResult) -> pd.DataFrame:
    rows = [
        ("Accumulated to date", integration.accumulated_hm3, "hm³"),
        ("Elevation of accumulation to date", integration.accumulated_elevation_m, "m"),
        ("Dead volume", integration.dead_vol_hm3, "hm³"),
    ]
    rows += [(f"Annual total, {name.lower()}", integration.rates[name], "hm³/yr") for name in RATE_NAMES]
    rows += [(f"Lifespan, {name} rate", *_lifespan(name, integration)) for name in RATE_NAMES]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _inputs_sheet(
    project: Project, dam: Dam, stamp: str, files: List[InputFile], parameters: List[Parameter]
) -> pd.DataFrame:
    rows = [
        ("Run", "App version", __version__, None, None),
        ("Run", "Timestamp", stamp, None, None),
        ("Run", "Project", project.name, None, None),
        ("Run", "Dam", dam.name, None, None),
    ]
    rows += [("Parameter", p.name, p.value, p.unit or None, None) for p in parameters]
    rows += [("File", f.role, f.path, None, f.sha256) for f in files]
    return pd.DataFrame(rows, columns=INPUT_COLUMNS)


def _write_workbook(
    path: Path,
    inputs: pd.DataFrame,
    suspended: SuspendedResult,
    bedload: BedloadResult,
    curve: CurveResult,
    integration: IntegrationResult,
    warnings: List[Tuple[str, str]],
) -> None:
    lowest, highest = integration.extremes
    extremes = pd.DataFrame([("Minimum", *lowest), ("Maximum", *highest)], columns=EXTREME_COLUMNS)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        inputs.to_excel(writer, sheet_name=INPUTS_SHEET, index=False)
        table_with_total(suspended).to_excel(writer, sheet_name="Suspended", index=False)
        bedload.table.to_excel(writer, sheet_name="Bedload", index=False)
        integration.annual.to_excel(writer, sheet_name="Annual", index=False)
        curve.table.to_excel(writer, sheet_name="Curve", index=False)
        integration.projection.to_excel(writer, sheet_name="Projection", index=False)
        # The extremes, then a blank row and the accumulation, rates and lifespans below them.
        extremes.to_excel(writer, sheet_name=EXTREMES_SHEET, index=False)
        _summary(integration).to_excel(writer, sheet_name=EXTREMES_SHEET, index=False, startrow=len(extremes) + 2)
        pd.DataFrame(warnings, columns=WARNING_COLUMNS).to_excel(writer, sheet_name=WARNINGS_SHEET, index=False)
        for sheet in writer.book.worksheets:  # text such as a sub-basin named "=1+1" is a name, not a formula
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.data_type == "f":
                        cell.data_type = "s"


def _write_run_json(
    path: Path,
    project: Project,
    dam: Dam,
    stamp: str,
    files: List[InputFile],
    parameters: List[Parameter],
    bedload: BedloadResult,
    curve: CurveResult,
    warnings: List[Tuple[str, str]],
) -> None:
    run = {
        "app_version": __version__,
        "timestamp": stamp,
        "project": project.name,
        "dam": {"name": dam.name, "slug": dam.slug},
        "inputs": [f._asdict() for f in files],
        "parameters": [p._asdict() for p in parameters],
        "flags": {
            "synthetic_flow": bedload.synthetic,
            "h_min_given": curve.h_min_given,
            "shape_class": curve.shape_class,
        },
        "warnings": [{"phase": phase, "text": text} for phase, text in warnings],
    }
    path.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _new_folder(outputs: Path, name: str) -> Path:
    """Create `outputs/name`, or `outputs/name_2`, ... when that already exists."""
    outputs.mkdir(parents=True, exist_ok=True)
    for attempt in itertools.count(1):
        folder = outputs / (name if attempt == 1 else f"{name}_{attempt}")
        try:
            folder.mkdir()
        except FileExistsError:
            continue
        return folder


def export_run(
    project: Project,
    dam: Dam,
    suspended: SuspendedResult,
    bedload: BedloadResult,
    curve: CurveResult,
    integration: IntegrationResult,
    input_warnings: Sequence[str] = (),
    now: Optional[datetime.datetime] = None,
) -> RunExport:
    """Write the run folder of `dam` and return it with the files written. `input_warnings` are those of the inputs
    (the zonal means and the dam sheet), which the results do not carry. Raises ValueError for a missing input."""
    now = now or datetime.datetime.now()
    stamp = now.isoformat(timespec="seconds")
    files = _input_files(project, dam)
    parameters = _parameters(dam, curve, integration)
    warnings = collect_warnings(input_warnings, suspended, bedload, curve, integration)

    folder = _new_folder(project.folder / "outputs", f"{dam.slug}_{now.strftime(STAMP_FORMAT)}")
    try:
        written = [
            write_suspended_csv(suspended, folder),
            write_bedload_csv(bedload, folder),
            write_reservoir_csv(curve, folder),
            write_integration_csv(integration, folder),
            write_projection_csv(integration, folder),
            write_bedload_trend(bedload.table, folder),
            write_annual_volume(integration, folder),
            write_reservoir_curve(curve, folder),
            write_projection(integration, folder),
        ]
        workbook = folder / WORKBOOK
        _write_workbook(
            workbook,
            _inputs_sheet(project, dam, stamp, files, parameters),
            suspended,
            bedload,
            curve,
            integration,
            warnings,
        )
        run_json = folder / RUN_JSON
        _write_run_json(run_json, project, dam, stamp, files, parameters, bedload, curve, warnings)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)  # a run folder holds a whole run or nothing
        raise
    return RunExport(folder, [*written, workbook, run_json])
