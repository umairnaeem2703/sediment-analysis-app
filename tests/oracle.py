"""The independent hand calculations in tests/verification/ as data (B6)."""

import csv
from pathlib import Path
from typing import Dict, List

VERIFICATION = Path(__file__).parent / "verification"


def _rows(name: str) -> List[dict]:
    """The rows of a verification CSV: numbers as floats, anything else (dates, labels) as text."""

    def convert(value: str):
        try:
            return float(value)
        except ValueError:
            return value

    with open(VERIFICATION / name, newline="", encoding="utf-8") as handle:
        return [{key: convert(value) for key, value in row.items()} for row in csv.DictReader(handle)]


def bedload_wstar() -> List[dict]:
    """B3.2 W* at a range of phi (columns Phi, W_star)."""
    return _rows("bedload_wstar.csv")


def bedload_tau_ri() -> List[dict]:
    """B3.2 reference exponent and stress per grain size (di_m, Fi, b_i, tau_ri_Pa). The first five, with Fi, are the sample."""
    return _rows("bedload_tau_ri.csv")


def bedload_transport() -> List[dict]:
    """B3.2 hydraulics and unit-width bedload of the sample fractions per flow (Flow_m3_s, Tau_Pa, U_star_m_s, Qb_m2_s)."""
    return _rows("bedload_transport.csv")


def bedload_series() -> List[dict]:
    """The daily series behind `bedload_annual()` (Date as dd/mm/yyyy, Flow, Water_Year, Qb_m2_s)."""
    return _rows("bedload_series.csv")


def bedload_annual() -> List[dict]:
    """The annual summary of the series by calendar and by water year (Grouping, Key, Mean_Flow_m3_s, Mean_Qb_m2_s, ...)."""
    return _rows("bedload_annual.csv")


def reservoir_cases() -> List[dict]:
    """The B3.3 fits (Hbed_m, Hmin_given_m, Hmax_m, Hcrest_m, Vactive_hm3, Vmax_hm3, Shape_Class, then Vdead_hm3, m,
    Hmin_m and Area_Hmax_km2). A blank Hmin_given_m or Shape_Class is the empty string."""
    return _rows("reservoir_cases.csv")


def reservoir_points() -> List[dict]:
    """The curve of each reservoir case at its bed, Hmin, mid-level, Hmax and crest (Case, Point, H_m, V_hm3, A_km2)."""
    return _rows("reservoir_points.csv")


def suspended_cases() -> Dict[int, dict]:
    """The B3.1 cases by case number: inputs and hand-calculated results as floats, plus the description."""
    with open(VERIFICATION / "suspended_cases.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        int(row["Case"]): {key: value if key == "Description" else float(value) for key, value in row.items()}
        for row in rows
    }
