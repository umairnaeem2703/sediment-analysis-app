"""The measured elevation-volume curve of one dam (FR-M4-01, FR-M4-02, B3.3, D75).

The curve is the hydrologist's table of level (m), volume (hm³) and surface area (km²), read between its rows by linear
interpolation and held at its first and last rows outside them. The dam sheet gives the operating values: Hbed (the
thalweg at the dam axis), Hmax, Hcrest, Vactive and Vmax. They need not lie on the curve: Vmax is the operating maximum,
not the curve's volume at Hmax (OI-11). Vdead = Vmax - Vactive and Hmin is the level of the curve at Vdead.
`check_table` checks the table itself and `check_fit` that the curve covers the dam sheet; `build_curve` refuses a
curve that fails either. `curve_warnings` holds the plausibility warning.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

LEVEL_TOLERANCE_M = 0.5  # the crest of the dam sheet against the curve's last level

ELEVATION_M, VOLUME_HM3, AREA_KM2 = "Elevation_m", "Volume_hm3", "Area_km2"


@dataclass(frozen=True)
class ReservoirCurve:
    levels_m: Tuple[float, ...]
    volumes_hm3: Tuple[float, ...]
    areas_km2: Tuple[float, ...]
    bed_elev_m: float
    max_elev_m: float
    crest_elev_m: float
    active_vol_hm3: float
    max_vol_hm3: float

    @property
    def dead_vol_hm3(self) -> float:
        return self.max_vol_hm3 - self.active_vol_hm3

    @property
    def h_min_m(self) -> float:
        """The level at which the reservoir holds only its dead volume."""
        return self.elevation(self.dead_vol_hm3)

    def volume(self, h):
        """V(H) in hm³."""
        result = np.interp(h, self.levels_m, self.volumes_hm3)
        return float(result) if np.ndim(h) == 0 else result

    def area(self, h):
        """A(H) in km²."""
        result = np.interp(h, self.levels_m, self.areas_km2)
        return float(result) if np.ndim(h) == 0 else result

    def elevation(self, v):
        """H(V) in m for a volume V in hm³."""
        result = np.interp(v, self.volumes_hm3, self.levels_m)
        return float(result) if np.ndim(v) == 0 else result

    def table(self) -> pd.DataFrame:
        """The rows of the curve: level, volume and surface area."""
        return pd.DataFrame(
            {ELEVATION_M: self.levels_m, VOLUME_HM3: self.volumes_hm3, AREA_KM2: self.areas_km2}, dtype=float
        )


def check_table(
    levels_m: Sequence[float],
    volumes_hm3: Sequence[float],
    areas_km2: Sequence[float],
    rows: Optional[Sequence[int]] = None,
) -> List[str]:
    """Every problem of the curve table: at least two rows, levels and volumes rising from row to row, and no volume or
    area below 0. `rows` names each row in the messages; by default they count from the header as row 1."""
    if len(levels_m) < 2:
        return [f"The curve needs at least two rows, found {len(levels_m)}."]
    rows = rows if rows is not None else range(2, len(levels_m) + 2)
    problems = []
    for position, row in enumerate(rows):
        if position and not levels_m[position] > levels_m[position - 1]:
            problems.append(f"row {row}: the level {levels_m[position]:g} m does not rise above the row before.")
        if position and not volumes_hm3[position] > volumes_hm3[position - 1]:
            problems.append(f"row {row}: the volume {volumes_hm3[position]:g} hm³ does not rise above the row before.")
        if volumes_hm3[position] < 0 or areas_km2[position] < 0:
            problems.append(f"row {row}: the volume and the surface area must not be below 0.")
    return problems


def check_fit(
    levels_m: Sequence[float],
    volumes_hm3: Sequence[float],
    *,
    bed_elev_m: float,
    max_elev_m: float,
    crest_elev_m: float,
    active_vol_hm3: float,
    max_vol_hm3: float,
) -> List[str]:
    """Every way the dam sheet does not fit a valid curve table, each naming the values: Hbed < Hmax <= Hcrest and
    0 < Vactive < Vmax; Hcrest within LEVEL_TOLERANCE_M of the curve's last level, so the curve reaches the crest; Hmax
    inside the curve; and Vdead inside the curve's volumes, so Hmin is read from it."""
    named = {
        "Hbed": bed_elev_m,
        "Hmax": max_elev_m,
        "Hcrest": crest_elev_m,
        "Vactive": active_vol_hm3,
        "Vmax": max_vol_hm3,
    }
    problems = [
        f"{name} must be a finite number, found {value}." for name, value in named.items() if not math.isfinite(value)
    ]
    if problems:
        return problems
    if not bed_elev_m < max_elev_m <= crest_elev_m:
        problems.append(
            f"The dam sheet must have Hbed ({bed_elev_m:g} m) < Hmax ({max_elev_m:g} m) <= Hcrest ({crest_elev_m:g} m)."
        )
    if not 0 < active_vol_hm3 < max_vol_hm3:
        problems.append(f"Vactive ({active_vol_hm3:g} hm³) must be above 0 and below Vmax ({max_vol_hm3:g} hm³).")
    first, last = levels_m[0], levels_m[-1]
    if abs(crest_elev_m - last) > LEVEL_TOLERANCE_M:
        problems.append(
            f"Hcrest on the dam sheet ({crest_elev_m:g} m) differs from the last level of the curve ({last:g} m) "
            f"by more than {LEVEL_TOLERANCE_M:g} m."
        )
    if not first <= max_elev_m <= last:
        problems.append(f"Hmax on the dam sheet ({max_elev_m:g} m) is outside the curve ({first:g} m to {last:g} m).")
    dead = max_vol_hm3 - active_vol_hm3
    if dead > 0 and not volumes_hm3[0] <= dead <= volumes_hm3[-1]:
        problems.append(
            f"Vdead = Vmax - Vactive ({dead:g} hm³) is outside the volumes of the curve "
            f"({volumes_hm3[0]:g} to {volumes_hm3[-1]:g} hm³), so Hmin cannot be read from it."
        )
    return problems


def build_curve(
    levels_m: Sequence[float],
    volumes_hm3: Sequence[float],
    areas_km2: Sequence[float],
    *,
    bed_elev_m: float,
    max_elev_m: float,
    crest_elev_m: float,
    active_vol_hm3: float,
    max_vol_hm3: float,
) -> ReservoirCurve:
    """The curve of the table with the dam sheet's values. Raises ValueError listing every problem of the table or, for
    a valid table, every way the dam sheet does not fit it."""
    levels, volumes, areas = (tuple(float(value) for value in column) for column in (levels_m, volumes_hm3, areas_km2))
    problems = check_table(levels, volumes, areas)
    if not problems:
        problems = check_fit(
            levels,
            volumes,
            bed_elev_m=bed_elev_m,
            max_elev_m=max_elev_m,
            crest_elev_m=crest_elev_m,
            active_vol_hm3=active_vol_hm3,
            max_vol_hm3=max_vol_hm3,
        )
    if problems:
        raise ValueError("The reservoir curve cannot be used:\n" + "\n".join(f"- {problem}" for problem in problems))
    return ReservoirCurve(levels, volumes, areas, bed_elev_m, max_elev_m, crest_elev_m, active_vol_hm3, max_vol_hm3)


def curve_warnings(curve: ReservoirCurve, drainage_area_km2: Optional[float] = None) -> List[str]:
    """The plausibility warning of FR-M4-01. The drainage area is the dam sheet's; without it nothing is compared."""
    area = curve.area(curve.max_elev_m)
    if drainage_area_km2 is not None and area > drainage_area_km2:
        return [f"The surface area at Hmax ({area:.2f} km²) is above the drainage area ({drainage_area_km2:g} km²)."]
    return []
