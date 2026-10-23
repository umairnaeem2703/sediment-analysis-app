"""The per-dam settings entered in step 3: commissioning and analysis year, trap efficiency and Hmin (A5, D7)."""

import datetime
import re
from typing import Dict, List, Optional, Tuple

from src.services.project import Dam, Project
from src.services.regional import cell_text, parse_number, quote_cell

_YEAR = re.compile(r"[0-9]{4}(?:[.,]0+)?")  # ASCII digits only: 1965 or 1965.0


def _year(label: str, value) -> Tuple[Optional[int], Optional[str]]:
    """(year, None) for a valid or blank entry, or (None, problem) for an invalid one."""
    text = cell_text(value)
    if not text:
        return None, None
    if not _YEAR.fullmatch(text):
        return None, f"{label} must be a four-digit whole number, found {quote_cell(value)}."
    return int(text[:4]), None


def validate_dam_settings(
    commissioning_year, analysis_year, trap_efficiency_pct, h_min_m
) -> Dict[str, Optional[float]]:
    """Convert the entered texts. A blank analysis year (None) means the current year; Hmin and the
    commissioning year are optional. Raises ValueError listing every problem."""
    commissioning, commissioning_problem = _year("Commissioning year", commissioning_year)
    analysis, analysis_problem = _year("Analysis year", analysis_year)
    problems: List[str] = [p for p in (commissioning_problem, analysis_problem) if p]

    efficiency = parse_number(trap_efficiency_pct)
    if efficiency is None or not 0 < efficiency <= 100:
        problems.append(
            f"Trap efficiency (%) must be a number above 0 and at most 100, found {quote_cell(trap_efficiency_pct)}."
        )

    h_min = None
    if cell_text(h_min_m):
        h_min = parse_number(h_min_m)
        if h_min is None:
            problems.append(f"Minimum operating level (Hmin, m) must be a number, found {quote_cell(h_min_m)}.")

    if commissioning is not None and not (commissioning_problem or analysis_problem):
        this_year = datetime.date.today().year
        if (analysis if analysis is not None else this_year) < commissioning:
            label = "Analysis year" if analysis is not None else f"Analysis year (the current year, {this_year})"
            problems.append(f"{label} is before the commissioning year ({commissioning}).")

    if problems:
        raise ValueError("The dam settings are not valid:\n" + "\n".join(f"- {problem}" for problem in problems))
    return {
        "commissioning_year": commissioning,
        "analysis_year": analysis,
        "trap_efficiency_pct": efficiency,
        "h_min_m": h_min,
    }


def apply_dam_settings(project: Project, dam: Dam, **entered) -> None:
    """Validate the entered texts and, only if they are all valid and saved, keep them on the dam."""
    values = validate_dam_settings(**entered)
    previous = {name: getattr(dam, name) for name in values}
    for name, value in values.items():
        setattr(dam, name, value)
    try:
        project.save()
    except OSError:
        for name, value in previous.items():
            setattr(dam, name, value)
        raise
