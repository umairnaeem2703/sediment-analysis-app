"""The reservoir elevation-volume curve of one dam (FR-M4-01, FR-M4-02, B3.3).

A power law `V(H) = Vmax * x**m` with `x = (H - Hbed) / (Hmax - Hbed)`, volumes in hm³, levels in m and areas in km²
(hm³ per m is 10⁶ m²). The exponent *m* is fitted through the dead-storage point (Hmin, Vdead) when Hmin is known and
is otherwise the exponent of the dam's shape class (D19).
"""

import math
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

SHAPE_CLASSES = {"gorge": 1.25, "hill": 2.0, "foothill": 3.0, "lake": 4.0}
EXPONENT_RANGE = (1.0, 4.5)  # a fitted m outside this is implausible (FR-M4-01)
MIN_DEPTH_M = 10.0  # Hmax - Hbed below this leaves the curve poorly constrained
STEP_M = 0.5  # the table's level step

ELEVATION_M, VOLUME_HM3, AREA_KM2 = "Elevation_m", "Volume_hm3", "Area_km2"


@dataclass(frozen=True)
class ReservoirCurve:
    bed_elev_m: float
    max_elev_m: float
    crest_elev_m: float
    active_vol_hm3: float
    max_vol_hm3: float
    exponent: float

    @property
    def dead_vol_hm3(self) -> float:
        return self.max_vol_hm3 - self.active_vol_hm3

    @property
    def h_min_m(self) -> float:
        """The level at which the reservoir holds only its dead volume."""
        return self.elevation(self.dead_vol_hm3)

    def _fraction(self, h):
        """x = (H - Hbed) / (Hmax - Hbed), zero at and below the bed."""
        return np.maximum(np.asarray(h, dtype=float) - self.bed_elev_m, 0.0) / (self.max_elev_m - self.bed_elev_m)

    def volume(self, h):
        """V(H) in hm³."""
        result = self.max_vol_hm3 * self._fraction(h) ** self.exponent
        return float(result) if np.ndim(h) == 0 else result

    def area(self, h):
        """A(H) = dV/dH = m V / (H - Hbed) in km², written as m Vmax / (Hmax - Hbed) x**(m - 1) so that the bed is defined
        (zero for m above 1, infinite below 1)."""
        scale = self.exponent * self.max_vol_hm3 / (self.max_elev_m - self.bed_elev_m)
        with np.errstate(divide="ignore"):
            result = scale * self._fraction(h) ** (self.exponent - 1.0)
        return float(result) if np.ndim(h) == 0 else result

    def elevation(self, v):
        """H(V) = Hbed + (Hmax - Hbed) (V / Vmax)**(1 / m) for a volume V in hm³ (the bed for V <= 0)."""
        v = np.maximum(np.asarray(v, dtype=float), 0.0)
        result = self.bed_elev_m + (self.max_elev_m - self.bed_elev_m) * (v / self.max_vol_hm3) ** (1.0 / self.exponent)
        return float(result) if np.ndim(v) == 0 else result


def check_inputs(
    *,
    bed_elev_m: float,
    h_min_m: Optional[float],
    max_elev_m: float,
    crest_elev_m: float,
    active_vol_hm3: float,
    max_vol_hm3: float,
) -> List[str]:
    """Every rule of FR-M4-01 the inputs break, in words: Hbed < Hmin < Hmax <= Hcrest and 0 < Vactive < Vmax. Hmin may
    be None."""
    problems = []
    named = {
        "Hbed": bed_elev_m,
        "Hmin": h_min_m,
        "Hmax": max_elev_m,
        "Hcrest": crest_elev_m,
        "Vactive": active_vol_hm3,
        "Vmax": max_vol_hm3,
    }
    for name, value in named.items():
        if value is not None and not math.isfinite(value):
            problems.append(f"{name} must be a finite number, found {value}.")
    if problems:
        return problems
    if not bed_elev_m < max_elev_m:
        problems.append(f"Hmax ({max_elev_m:g} m) must be above Hbed ({bed_elev_m:g} m).")
    if h_min_m is not None and not bed_elev_m < h_min_m < max_elev_m:
        problems.append(
            f"Hmin ({h_min_m:g} m) must be above Hbed ({bed_elev_m:g} m) and below Hmax ({max_elev_m:g} m)."
        )
    if not max_elev_m <= crest_elev_m:
        problems.append(f"Hcrest ({crest_elev_m:g} m) must not be below Hmax ({max_elev_m:g} m).")
    if not 0 < active_vol_hm3 < max_vol_hm3:
        problems.append(f"Vactive ({active_vol_hm3:g} hm³) must be above 0 and below Vmax ({max_vol_hm3:g} hm³).")
    return problems


def check_shape(h_min_m: Optional[float], shape_class: Optional[str]) -> List[str]:
    """Hmin or a known shape class must fix the curve; a shape class that is given must be known."""
    if shape_class is not None and shape_class not in SHAPE_CLASSES:
        return [f"The shape class '{shape_class}' is unknown (gorge, hill, foothill or lake)."]
    if h_min_m is None and shape_class is None:
        return ["Enter Hmin or a shape class: one of them fixes the curve."]
    return []


def fit_curve(
    *,
    bed_elev_m: float,
    max_elev_m: float,
    crest_elev_m: float,
    active_vol_hm3: float,
    max_vol_hm3: float,
    h_min_m: Optional[float] = None,
    shape_class: Optional[str] = None,
) -> ReservoirCurve:
    """The curve through (Hbed, 0) and (Hmax, Vmax), and through (Hmin, Vdead) when Hmin is given; otherwise the exponent
    is that of `shape_class`. Raises ValueError listing every problem with the inputs."""
    problems = check_inputs(
        bed_elev_m=bed_elev_m,
        h_min_m=h_min_m,
        max_elev_m=max_elev_m,
        crest_elev_m=crest_elev_m,
        active_vol_hm3=active_vol_hm3,
        max_vol_hm3=max_vol_hm3,
    ) + check_shape(h_min_m, shape_class)
    if problems:
        raise ValueError("The curve inputs are not valid:\n" + "\n".join(f"- {problem}" for problem in problems))

    if h_min_m is None:
        exponent = SHAPE_CLASSES[shape_class]
    else:
        dead_fraction = (max_vol_hm3 - active_vol_hm3) / max_vol_hm3
        exponent = math.log(dead_fraction) / math.log((h_min_m - bed_elev_m) / (max_elev_m - bed_elev_m))
    return ReservoirCurve(bed_elev_m, max_elev_m, crest_elev_m, active_vol_hm3, max_vol_hm3, exponent)


def curve_warnings(curve: ReservoirCurve, drainage_area_km2: Optional[float] = None) -> List[str]:
    """The plausibility warnings of FR-M4-01. The drainage area is the dam sheet's; without it nothing is compared."""
    warnings = []
    low, high = EXPONENT_RANGE
    if not low <= curve.exponent <= high:
        warnings.append(f"The fitted exponent m = {curve.exponent:.2f} is outside the usual range {low:g} to {high:g}.")
    depth = curve.max_elev_m - curve.bed_elev_m
    if depth < MIN_DEPTH_M:
        warnings.append(
            f"Hmax is only {depth:.1f} m above Hbed, below {MIN_DEPTH_M:g} m: the curve is poorly constrained."
        )
    area = curve.area(curve.max_elev_m)
    if drainage_area_km2 is not None and area > drainage_area_km2:
        warnings.append(
            f"The surface area at Hmax ({area:.2f} km²) is above the drainage area ({drainage_area_km2:g} km²)."
        )
    return warnings


def curve_table(curve: ReservoirCurve) -> pd.DataFrame:
    """Level, volume and surface area every 0.5 m from the bed to the crest; a crest off that grid closes the table."""
    steps = int((curve.crest_elev_m - curve.bed_elev_m) / STEP_M + 1e-9)
    levels = curve.bed_elev_m + STEP_M * np.arange(steps + 1)
    if curve.crest_elev_m - levels[-1] > 1e-9:
        levels = np.append(levels, curve.crest_elev_m)
    return pd.DataFrame({ELEVATION_M: levels, VOLUME_HM3: curve.volume(levels), AREA_KM2: curve.area(levels)})
