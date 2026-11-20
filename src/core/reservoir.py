"""The measured elevation-volume curve of one dam (FR-M4-01, FR-M4-02, B3.3, D75, D76).

The curve is the hydrologist's table of level (m), volume (hm³) and surface area (km²), read between its rows by linear
interpolation and held at its first and last rows outside them. The curve alone gives Hbed (its first level), Hcrest
(its last level) and Vmax (its last volume); the one other input is Hmin, the minimum operating level, entered in step 6,
and Vdead = V(Hmin) (D76). `check_table` checks the table itself and `check_h_min` that Hmin lies inside it;
`build_curve` refuses a curve that fails either.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ELEVATION_M, VOLUME_HM3, AREA_KM2 = "Elevation_m", "Volume_hm3", "Area_km2"


@dataclass(frozen=True)
class ReservoirCurve:
    levels_m: Tuple[float, ...]
    volumes_hm3: Tuple[float, ...]
    areas_km2: Tuple[float, ...]
    h_min_m: float  # the minimum operating level, entered in step 6

    @property
    def bed_elev_m(self) -> float:
        """Hbed, the first level of the curve."""
        return self.levels_m[0]

    @property
    def crest_elev_m(self) -> float:
        """Hcrest, the last level of the curve."""
        return self.levels_m[-1]

    @property
    def max_vol_hm3(self) -> float:
        """Vmax, the volume at the crest."""
        return self.volumes_hm3[-1]

    @property
    def dead_vol_hm3(self) -> float:
        """Vdead = V(Hmin), the volume below the minimum operating level."""
        return self.volume(self.h_min_m)

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


def check_h_min(levels_m: Sequence[float], h_min_m: float) -> List[str]:
    """Every problem of Hmin against a valid curve table: it must lie strictly between Hbed (the first level) and
    Hcrest (the last level), so the dead volume V(Hmin) is read from the curve."""
    if not math.isfinite(h_min_m):
        return [f"Hmin must be a finite number, found {h_min_m}."]
    first, last = levels_m[0], levels_m[-1]
    if not first < h_min_m < last:
        return [f"Hmin ({h_min_m:g} m) must lie above Hbed ({first:g} m) and below Hcrest ({last:g} m) of the curve."]
    return []


def build_curve(
    levels_m: Sequence[float], volumes_hm3: Sequence[float], areas_km2: Sequence[float], *, h_min_m: float
) -> ReservoirCurve:
    """The curve of the table with the entered Hmin. Raises ValueError listing every problem of the table or, for a
    valid table, the problem of Hmin."""
    levels, volumes, areas = (tuple(float(value) for value in column) for column in (levels_m, volumes_hm3, areas_km2))
    problems = check_table(levels, volumes, areas) or check_h_min(levels, h_min_m)
    if problems:
        raise ValueError("The reservoir curve cannot be used:\n" + "\n".join(f"- {problem}" for problem in problems))
    return ReservoirCurve(levels, volumes, areas, float(h_min_m))
