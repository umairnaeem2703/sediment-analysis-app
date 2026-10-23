"""The per-dam settings entered in step 3: commissioning and analysis year, trap efficiency and Hmin (A5, D7)."""

import datetime
from typing import Dict, List, Optional

from src.services.project import Dam, Project
from src.services.regional import _number, _shown, _text


def _year(label: str, value, problems: List[str]) -> Optional[int]:
    """A four-digit whole-number year, or None when blank or invalid (invalid ones add a problem)."""
    if not _text(value):
        return None
    number = _number(value)
    if number is None or number != int(number) or not 1000 <= number <= 9999:
        problems.append(f"{label} must be a four-digit whole number, found {_shown(value)}.")
        return None
    return int(number)


def validate_dam_settings(
    commissioning_year, analysis_year, trap_efficiency_pct, h_min_m
) -> Dict[str, Optional[float]]:
    """Convert the entered texts. A blank analysis year (None) means the current year; Hmin and the
    commissioning year are optional. Raises ValueError listing every problem."""
    problems: List[str] = []
    commissioning = _year("Commissioning year", commissioning_year, problems)
    years_valid = len(problems) == 0
    analysis = _year("Analysis year", analysis_year, problems)
    years_valid = years_valid and len(problems) == 0

    efficiency = _number(trap_efficiency_pct)
    if efficiency is None or not 0 < efficiency <= 100:
        problems.append(
            f"Trap efficiency (%) must be a number above 0 and at most 100, found {_shown(trap_efficiency_pct)}."
        )

    h_min = None
    if _text(h_min_m):
        h_min = _number(h_min_m)
        if h_min is None:
            problems.append(f"Minimum operating level (Hmin, m) must be a number, found {_shown(h_min_m)}.")

    if years_valid and commissioning is not None:
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
    """Validate the entered texts and, only if they are all valid, store them on the dam and save the project."""
    for name, value in validate_dam_settings(**entered).items():
        setattr(dam, name, value)
    project.save()
