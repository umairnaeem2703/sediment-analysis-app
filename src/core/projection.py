"""Accumulation to date, projection and lifespan of a reservoir (FR-M4-04, FR-M4-05, B3.4).

Volumes are in hm³ and rates in hm³/yr. The years are the labels of the record, used as they are (a DSİ water year
keeps its label).
"""

import math
from typing import Dict, List, NamedTuple, Optional

import numpy as np
import pandas as pd

RATE_NAMES = ("Mean", "Min", "Max")
# The default length of the projection, in years past the analysis year (the user may enter another).
HORIZON_YEARS = 100
MAX_HORIZON_YEARS = 1000  # a longer table only makes the grid and the chart unusable (D69)

YEAR, EXCEEDED, NOT_REACHED = "year", "exceeded", "not reached"


class Accumulation(NamedTuple):
    table: pd.DataFrame  # Year, In_Record, Total_Used_hm3, Cumulative_hm3: one row for each year from c to a - 1
    volume_hm3: float  # S0, the volume accumulated before the analysis year


class Lifespan(NamedTuple):
    status: str  # YEAR, EXCEEDED (the dead volume was passed before the analysis year) or NOT_REACHED
    year: Optional[float]  # a + (Vdead - S0) / r when the status is YEAR


def annual_rates(totals) -> Dict[str, float]:
    """The mean, minimum and maximum annual total of the whole record."""
    totals = np.asarray(totals, dtype=float)
    return {"Mean": float(totals.mean()), "Min": float(totals.min()), "Max": float(totals.max())}


def accumulate(years, totals, commissioning_year: int, analysis_year: int) -> Accumulation:
    """S0 = the sum of T'(y) for c <= y < a, where T'(y) is the record's total for y and the mean total for a year the
    record does not hold. Record years before commissioning are left out; the mean is over the whole record."""
    if analysis_year < commissioning_year:
        raise ValueError(
            f"The analysis year ({analysis_year}) is before the commissioning year ({commissioning_year})."
        )
    record = dict(zip((int(year) for year in years), np.asarray(totals, dtype=float)))
    mean = float(np.mean(list(record.values())))
    span = range(commissioning_year, analysis_year)
    used = [record.get(year, mean) for year in span]
    cumulative = np.cumsum(used)
    table = pd.DataFrame(
        {
            "Year": list(span),
            "In_Record": [int(year in record) for year in span],
            "Total_Used_hm3": used,
            "Cumulative_hm3": cumulative,
        }
    )
    return Accumulation(table, float(cumulative[-1]) if used else 0.0)  # the same sum as the table's, to the last digit


def exceeded_year(table: pd.DataFrame, dead_vol_hm3: float) -> Optional[int]:
    """The first year whose cumulative volume reaches the dead volume, or None."""
    reached = table.loc[table["Cumulative_hm3"] >= dead_vol_hm3, "Year"]
    return int(reached.iloc[0]) if len(reached) else None


def check_horizon(years: float) -> List[str]:
    """The projection length must be a whole number of years, from 1 to MAX_HORIZON_YEARS."""
    if math.isfinite(years) and 1 <= years <= MAX_HORIZON_YEARS and float(years).is_integer():
        return []
    return [f"The number of projection years ({years:g}) must be a whole number from 1 to {MAX_HORIZON_YEARS}."]


def project(
    accumulated_hm3: float, rate_hm3_yr: float, analysis_year: int, horizon: int = HORIZON_YEARS
) -> pd.DataFrame:
    """S(a + k) = S0 + k · r for k = 0 to `horizon` years (100 by default). Raises ValueError for an invalid horizon."""
    problems = check_horizon(horizon)
    if problems:
        raise ValueError("\n".join(problems))
    k = np.arange(int(horizon) + 1)
    return pd.DataFrame({"Year": analysis_year + k, "Cumulative_hm3": accumulated_hm3 + k * rate_hm3_yr})


def lifespan(dead_vol_hm3: float, accumulated_hm3: float, rate_hm3_yr: float, analysis_year: int) -> Lifespan:
    """The year the cumulative volume reaches the dead volume, a + (Vdead - S0) / r. Nothing is left to fill when
    S0 >= Vdead (that wins over a zero rate), and a zero rate never fills it."""
    if accumulated_hm3 >= dead_vol_hm3:
        return Lifespan(EXCEEDED, None)
    if rate_hm3_yr == 0:
        return Lifespan(NOT_REACHED, None)
    return Lifespan(YEAR, analysis_year + (dead_vol_hm3 - accumulated_hm3) / rate_hm3_yr)
