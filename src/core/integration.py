"""Annual sediment totals and the elevations they reach in the reservoir (FR-M4-03, B3.4).

Volumes are in hm³ from here on (m³ / 10⁶). A volume above the one at the crest is limited to the crest elevation and
counted, so that the caller can warn.
"""

from typing import NamedTuple, Tuple

import numpy as np

from src.core.reservoir import ReservoirCurve

M3_PER_HM3 = 1_000_000.0


class Extreme(NamedTuple):
    year: int
    total_hm3: float
    elevation_m: float


def retained_hm3(volume_m3, trap_efficiency_pct: float) -> np.ndarray:
    """The part of a volume in m³ that stays in the reservoir, in hm³: TE · V, with the trap efficiency as a percentage."""
    return trap_efficiency_pct / 100.0 * np.asarray(volume_m3, dtype=float) / M3_PER_HM3


def annual_totals(bedload_m3_yr, suspended_m3_yr: float, trap_efficiency_pct: float) -> np.ndarray:
    """T(y) = TE · (Vs + Vb(y)) in hm³ for each bedload volume Vb(y)."""
    return retained_hm3(suspended_m3_yr + np.asarray(bedload_m3_yr, dtype=float), trap_efficiency_pct)


def sediment_elevations(curve: ReservoirCurve, volumes_hm3) -> Tuple[np.ndarray, int]:
    """H(S) for each volume S, with the volumes above V(Hcrest) set to Hcrest, and how many of them there were."""
    volumes = np.asarray(volumes_hm3, dtype=float)
    above = volumes > curve.volume(curve.crest_elev_m)
    elevations = np.where(above, curve.crest_elev_m, curve.elevation(volumes))
    return elevations, int(above.sum())


def extremes(years, totals_hm3, elevations_m) -> Tuple[Extreme, Extreme]:
    """The years of the minimum and the maximum annual total (FR-M5-01), with each year's total and elevation. A tie
    goes to the earliest year."""
    if len(years) == 0:
        raise ValueError("There are no years to take the minimum and maximum of.")
    rows = [
        Extreme(int(year), float(total), float(elevation))
        for year, total, elevation in zip(years, totals_hm3, elevations_m, strict=True)
    ]
    return min(rows, key=lambda row: (row.total_hm3, row.year)), min(rows, key=lambda row: (-row.total_hm3, row.year))
