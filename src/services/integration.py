"""Integration, accumulation and lifespan of one dam (FR-M4-03 to FR-M4-05, B3.4).

`compute_dam_integration` joins the dam's suspended total, its annual bedload and its reservoir curve with the dam's
trap efficiency, commissioning year and analysis year. `write_integration_csv` and `write_projection_csv` write
`integration.csv` and `projection.csv` into a folder they are given; the run folder itself belongs to the reporting
service (M5).
"""

import datetime
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

import numpy as np
import pandas as pd

from src.core.integration import Extreme, annual_totals, extremes, retained_hm3, sediment_elevations
from src.core.projection import (
    HORIZON_YEARS,
    RATE_NAMES,
    Lifespan,
    accumulate,
    annual_rates,
    check_horizon,
    exceeded_year,
    lifespan,
    project,
)
from src.core.reservoir import ReservoirCurve
from src.services.bedload import VOLUME_M3, BedloadResult
from src.services.project import Dam
from src.services.regional import parse_number, quote_cell
from src.services.reservoir import CurveResult
from src.services.suspended import SuspendedResult

INTEGRATION_CSV = "integration.csv"
PROJECTION_CSV = "projection.csv"

# Output columns are named for their units (A7). The annual table starts with the bedload table's year key.
SUSPENDED_HM3, BEDLOAD_HM3, TOTAL_HM3, ELEVATION_M = "Suspended_hm3", "Bedload_hm3", "Total_hm3", "Elevation_m"
PROJECTION_COLUMNS = (
    ["Year"] + [f"Cumulative_{name}_hm3" for name in RATE_NAMES] + [f"Elevation_{name}_m" for name in RATE_NAMES]
)


class IntegrationResult(NamedTuple):
    # The year key, then what stays in the reservoir: suspended, bedload, total (hm³) and its elevation.
    annual: pd.DataFrame
    accumulation: pd.DataFrame  # Year, In_Record, Total_Used_hm3, Cumulative_hm3, for c <= y < a
    rates: Dict[str, float]  # Mean, Min and Max annual total, hm³/yr
    accumulated_hm3: float  # S0
    accumulated_elevation_m: float
    exceeded_year: Optional[int]  # the year the cumulative volume reached the dead volume, if it already has
    lifespans: Dict[str, Lifespan]  # by rate
    projection: pd.DataFrame  # PROJECTION_COLUMNS, from the analysis year to the horizon (100 years by default) later
    commissioning_year: int
    analysis_year: int
    trap_efficiency_pct: float
    dead_vol_hm3: float
    h_min_m: float
    warnings: List[str]

    @property
    def year_column(self) -> str:
        return self.annual.columns[0]

    @property
    def extremes(self) -> Tuple[Extreme, Extreme]:
        """The years of the minimum and the maximum annual total, with their totals and elevations (FR-M5-01)."""
        return extremes(self.annual[self.year_column], self.annual[TOTAL_HM3], self.annual[ELEVATION_M])


def parse_horizon(text) -> int:
    """The projection length in years, as entered in step 7: a whole number of at least 1. Raises ValueError."""
    years = parse_number(text)
    if years is None:
        raise ValueError(f"The number of projection years must be a number, found {quote_cell(text)}.")
    problems = check_horizon(years)
    if problems:
        raise ValueError("\n".join(problems))
    return int(years)


def compute_integration(
    suspended_m3_yr: float,
    bedload: BedloadResult,
    curve: ReservoirCurve,
    *,
    trap_efficiency_pct: float,
    commissioning_year: Optional[int],
    analysis_year: int,
    horizon_years: int = HORIZON_YEARS,
) -> IntegrationResult:
    """The annual totals and elevations of the record, the accumulation to date, and the projection over `horizon_years`
    and the lifespan at the mean, minimum and maximum rates (B3.4). A commissioning year is needed."""
    if commissioning_year is None:
        raise ValueError(
            "The commissioning year is needed to accumulate the sediment to date: enter it in step 3 (Select dam)."
        )
    if bedload.table.empty:
        raise ValueError("There are no bedload years to integrate.")
    year_column = bedload.year_column
    years, bedload_m3 = bedload.table[year_column], bedload.table[VOLUME_M3]

    totals = annual_totals(bedload_m3, suspended_m3_yr, trap_efficiency_pct)
    elevations, over_the_crest = sediment_elevations(curve, totals)
    annual = pd.DataFrame(
        {
            year_column: years,
            SUSPENDED_HM3: retained_hm3(np.full(len(years), suspended_m3_yr), trap_efficiency_pct),
            BEDLOAD_HM3: retained_hm3(bedload_m3, trap_efficiency_pct),
            TOTAL_HM3: totals,
            ELEVATION_M: elevations,
        }
    )
    accumulation = accumulate(years, totals, commissioning_year, analysis_year)
    rates = annual_rates(totals)
    accumulated_elevation, accumulated_over = sediment_elevations(curve, [accumulation.volume_hm3])

    projection = pd.DataFrame({"Year": analysis_year + np.arange(horizon_years + 1)})
    projected_over = 0
    for name in RATE_NAMES:
        volumes = project(accumulation.volume_hm3, rates[name], analysis_year, horizon_years)["Cumulative_hm3"]
        projected_elevations, count = sediment_elevations(curve, volumes)
        projection[f"Cumulative_{name}_hm3"], projection[f"Elevation_{name}_m"] = volumes, projected_elevations
        projected_over += count

    warnings = _warnings(
        curve, over_the_crest, int(accumulated_over), projected_over, int((accumulation.table["In_Record"] == 0).sum())
    )
    return IntegrationResult(
        annual=annual,
        accumulation=accumulation.table,
        rates=rates,
        accumulated_hm3=accumulation.volume_hm3,
        accumulated_elevation_m=float(accumulated_elevation[0]),
        exceeded_year=exceeded_year(accumulation.table, curve.dead_vol_hm3),
        lifespans={
            name: lifespan(curve.dead_vol_hm3, accumulation.volume_hm3, rates[name], analysis_year)
            for name in RATE_NAMES
        },
        projection=projection[PROJECTION_COLUMNS],
        commissioning_year=commissioning_year,
        analysis_year=analysis_year,
        trap_efficiency_pct=trap_efficiency_pct,
        dead_vol_hm3=curve.dead_vol_hm3,
        h_min_m=curve.h_min_m,
        warnings=warnings,
    )


def _warnings(
    curve: ReservoirCurve, annual_over: int, accumulated_over: int, projected_over: int, outside: int
) -> List[str]:
    crest = f"the volume at the crest ({curve.volume(curve.crest_elev_m):,.1f} hm³)"
    warnings = []
    if outside:
        warnings.append(
            f"{outside} year(s) between the commissioning year and the analysis year are not in the record; "
            "the mean annual total was used for them."
        )
    if annual_over:
        warnings.append(
            f"{annual_over} year(s) of the record deliver more than {crest}; their elevations are limited to Hcrest."
        )
    if accumulated_over:
        warnings.append(f"The accumulation to date is above {crest}; its elevation is limited to Hcrest.")
    if projected_over:
        warnings.append(
            f"{projected_over} projected value(s) are above {crest}; their elevations are limited to Hcrest."
        )
    return warnings


def compute_dam_integration(
    suspended: SuspendedResult,
    bedload: BedloadResult,
    curve: CurveResult,
    dam: Dam,
    this_year: Optional[int] = None,
    horizon_years: int = HORIZON_YEARS,
) -> IntegrationResult:
    """The dam's integration from its step 4 to 6 results and its step 3 settings. A blank analysis year is `this_year`
    (the current year when that is not given). The projection runs `horizon_years` past the analysis year."""
    analysis_year = dam.analysis_year or this_year or datetime.date.today().year
    return compute_integration(
        suspended.total_volume_m3,
        bedload,
        curve.curve,
        trap_efficiency_pct=dam.trap_efficiency_pct,
        commissioning_year=dam.commissioning_year,
        analysis_year=analysis_year,
        horizon_years=horizon_years,
    )


def write_integration_csv(result: IntegrationResult, folder) -> Path:
    """Write the annual table to `folder/integration.csv` (UTF-8 with BOM, for Excel)."""
    path = Path(folder) / INTEGRATION_CSV
    result.annual.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def write_projection_csv(result: IntegrationResult, folder) -> Path:
    """Write the projection to `folder/projection.csv` (UTF-8 with BOM, for Excel)."""
    path = Path(folder) / PROJECTION_CSV
    result.projection.to_csv(path, index=False, encoding="utf-8-sig")
    return path
