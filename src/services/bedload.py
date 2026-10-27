"""Bedload of one dam (FR-M3-01 to FR-M3-05, B3.2).

`load_flow` and `load_fractions` read and check the two inputs; `import_flow` and `import_fractions` copy them into the
project (the file the user picked is only read). `compute_bedload` turns a flow series and the grain fractions into the
annual table, and `compute_dam_bedload` does so from the copies held by a project. `write_bedload_csv` writes
`bedload.csv` into a folder it is given; the run folder itself belongs to the reporting service (M5).
"""

import re
from pathlib import Path
from typing import List, NamedTuple, Tuple

import pandas as pd

from src.core.monthly_flow_preprocessor import DEFAULT_PHI, is_monthly_flow_table, prepare_daily_flow
from src.core.rusle import normalize_header
from src.core.wilcock import FractionalModel, TimeSeriesAggregator
from src.services.project import Dam, Flow, Project
from src.services.regional import (
    Loaded,
    Problem,
    TableError,
    _is_blank,
    _missing_columns_error,
    cell_text,
    parse_number,
    quote_cell,
    read_input,
)

CSV_NAME = "bedload.csv"

# Output columns are named for their units (A7). The first column of the table is the year key: Water_Year or Year.
FLOW_M3_S, QB_M2_S, VOLUME_M3, MASS_T = "Mean_Flow_m3_s", "Mean_Qb_m2_s", "Volume_m3_yr", "Mass_t_yr"
_SUMMARY_COLUMNS = {
    "Annual_Average_Flow": FLOW_M3_S,
    "Average_Rate_m2_s": QB_M2_S,
    "Annual_Total_Bedload_m3_yr": VOLUME_M3,
    "Annual_Average_Bed_Load_metric_tons_yr": MASS_T,
}
VALUE_COLUMNS = list(_SUMMARY_COLUMNS.values())

# Any valid fractions will do: summarising with them only checks the flow series.
_CHECK_FRACTIONS = pd.DataFrame({"di": [0.02], "Fi": [1.0]})
_FRACTION_ALIASES = {"di": ("di",), "Fi": ("fi",), "bi": ("bi",), "tau_ri": ("tau_ri", "tau_ri(pa)", "tauri")}


class FlowSeries(NamedTuple):
    daily: pd.DataFrame  # a daily series as read, or the Date, Flow and Water_Year series made from a DSİ monthly table
    synthetic: bool  # True when the daily flow was made from monthly volumes (D10)
    notes: List[str]


class BedloadResult(NamedTuple):
    table: pd.DataFrame  # the year key, then VALUE_COLUMNS; one row per water year or calendar year
    synthetic: bool
    notes: List[str]
    warnings: List[str]

    @property
    def year_column(self) -> str:
        return self.table.columns[0]

    @property
    def mean_volume_m3_yr(self) -> float:
        return float(self.table[VOLUME_M3].mean())


def _message(exc: Exception) -> str:
    return str(exc.args[0]) if isinstance(exc, KeyError) else str(exc)  # str(KeyError) wraps the text in quotes


# --- inputs -----------------------------------------------------------------------------------


def load_flow(path, sigma: float, seed: int, phi: float = DEFAULT_PHI) -> FlowSeries:
    """Read a flow file. A DSİ monthly table is split into a synthetic daily series with `sigma`, `seed` and the lag-1
    `phi` (D10, D62); a daily series is returned as read and checked when it is summarised."""
    source = Path(path).name
    table = read_input(path)
    if not is_monthly_flow_table(table):
        return FlowSeries(table, False, [])
    try:
        daily, notes = prepare_daily_flow(table, sigma, seed, phi)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{source}: {_message(exc)}") from exc
    return FlowSeries(daily, True, notes)


def load_fractions(path) -> Loaded:
    """The grain fractions as numbers: `di` (m) and `Fi`, plus `bi` and `tau_ri` when the file has them. The warnings are
    the cross-check of those two columns (D36)."""
    source = Path(path).name
    table = read_input(path)
    names = {normalize_header(column): column for column in table.columns}
    found = {key: next((names[a] for a in aliases if a in names), None) for key, aliases in _FRACTION_ALIASES.items()}
    missing = [key for key in ("di", "Fi") if found[key] is None]
    if missing:
        raise _missing_columns_error(source, missing, table)

    present_keys = [key for key, column in found.items() if column is not None]
    rows, problems = [], []
    for position, (_, record) in enumerate(table.iterrows()):
        if _is_blank(record):
            continue
        row, entry = position + 2, {}
        for key in present_keys:
            raw = record[found[key]]
            entry[key] = parse_number(raw)
            if entry[key] is None and (key in ("di", "Fi") or cell_text(raw)):
                problems.append(
                    Problem(f"row {row}: '{key}' must be a number, found {quote_cell(raw)}.", ((row, key),))
                )
            elif entry[key] is None:
                entry[key] = float("nan")  # an optional column left blank: nothing to cross-check
        rows.append(entry)
    if problems:
        raise TableError(source, problems)
    if not rows:
        raise ValueError(f"{source}: no grain fractions found.")

    frame = pd.DataFrame(rows, columns=present_keys)
    model = FractionalModel()
    try:
        model.load_fractional_parameters(frame)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{source}: {_message(exc)}") from exc
    return Loaded(frame, [f"{source}: {warning}" for warning in model.warnings])


def validate_flow_settings(sigma, seed, phi="0") -> Tuple[float, int, float]:
    """Convert the entered sigma, seed and lag-1 phi of the monthly split. Raises ValueError listing every problem."""
    problems = []
    sigma_value = parse_number(sigma)
    if sigma_value is None or sigma_value < 0:
        problems.append(f"Sigma must be a number of at least 0, found {quote_cell(sigma)}.")
    seed_text = cell_text(seed)
    if not re.fullmatch(r"[0-9]+", seed_text):  # ASCII digits only
        problems.append(f"Seed must be a whole number of at least 0, found {quote_cell(seed)}.")
    phi_value = parse_number(phi)
    if phi_value is None or not 0 <= phi_value < 1:
        problems.append(f"Lag-1 phi must be a number from 0 up to, but not including, 1, found {quote_cell(phi)}.")
    if problems:
        raise ValueError("The flow settings are not valid:\n" + "\n".join(f"- {problem}" for problem in problems))
    return sigma_value, int(seed_text), phi_value


def apply_flow_settings(project: Project, dam: Dam, sigma, seed, phi="0") -> bool:
    """Validate the entered texts and keep them on the dam if they are all valid and saved. True if they changed."""
    values = validate_flow_settings(sigma, seed, phi)
    previous = (dam.flow.sigma, dam.flow.seed, dam.flow.phi)
    if values == previous:
        return False
    dam.flow.sigma, dam.flow.seed, dam.flow.phi = values
    try:
        project.save()
    except OSError:
        dam.flow.sigma, dam.flow.seed, dam.flow.phi = previous
        raise
    return True


def import_flow(project: Project, dam: Dam, path, sigma: float, seed: int, phi: float = DEFAULT_PHI) -> FlowSeries:
    """Check a flow file and copy it into the project as the dam's flow, with the sigma, seed and phi to split it with.
    A file that cannot be read, converted or summarised raises and nothing is copied."""
    series = load_flow(path, sigma, seed, phi)
    compute_bedload(series, _CHECK_FRACTIONS, Path(path).name)
    relative = project.import_file(path, f"inputs/flow/{dam.slug}_flow{Path(path).suffix.lower()}")
    previous = dam.flow
    dam.flow = Flow(relative, sigma, seed, phi)
    try:
        project.save()
    except OSError:
        dam.flow = previous
        raise
    if previous.path and previous.path != relative:
        (project.folder / previous.path).unlink(missing_ok=True)
    return series


def import_fractions(project: Project, path) -> Loaded:
    """Check a grain fractions file and copy it into the project. An unusable file raises and nothing is copied."""
    loaded = load_fractions(path)
    relative = project.import_file(path, f"inputs/fractions{Path(path).suffix.lower()}")
    previous = project.inputs.get("fractions")
    project.inputs["fractions"] = relative
    try:
        project.save()
    except OSError:
        project.inputs["fractions"] = previous
        raise
    if previous and previous != relative:
        (project.folder / previous).unlink(missing_ok=True)
    return loaded


# --- bedload ----------------------------------------------------------------------------------


def compute_bedload(
    flow: FlowSeries,
    fractions: pd.DataFrame,
    flow_source: str = "the flow file",
    fractions_source: str = "the fractions",
) -> BedloadResult:
    """The annual bedload of a daily flow series (B3.2). The sources name the inputs in error and warning messages."""
    model = FractionalModel()
    try:
        model.load_fractional_parameters(fractions)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{fractions_source}: {_message(exc)}") from exc
    aggregator = TimeSeriesAggregator(model)
    try:
        summary = aggregator.process_annual_averages(flow.daily)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{flow_source}: {_message(exc)}") from exc
    key = summary.index.name
    table = summary.reset_index().rename(columns=_SUMMARY_COLUMNS)[[key, *VALUE_COLUMNS]]
    warnings = [f"{fractions_source}: {warning}" for warning in model.warnings]
    warnings += [f"{flow_source}: {warning}" for warning in aggregator.warnings]
    return BedloadResult(table, flow.synthetic, flow.notes, warnings)


def compute_dam_bedload(project: Project, dam: Dam) -> BedloadResult:
    """The dam's bedload from the copies in the project folder. A missing input is an error naming it (FR-X-01)."""
    if not dam.flow.path:
        raise ValueError(f"No flow file has been chosen for {dam.name}.")
    fractions_path = project.inputs.get("fractions")
    if not fractions_path:
        raise ValueError("No grain fractions file has been chosen.")
    flow_file, fractions_file = project.folder / dam.flow.path, project.folder / fractions_path
    flow = load_flow(flow_file, dam.flow.sigma, dam.flow.seed, dam.flow.phi)
    fractions = load_fractions(fractions_file)
    return compute_bedload(flow, fractions.data, flow_file.name, fractions_file.name)


def write_bedload_csv(result: BedloadResult, folder) -> Path:
    """Write the annual table to `folder/bedload.csv` (UTF-8 with BOM, for Excel)."""
    path = Path(folder) / CSV_NAME
    result.table.to_csv(path, index=False, encoding="utf-8-sig")
    return path
