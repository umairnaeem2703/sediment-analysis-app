import math
from pathlib import Path

import numpy as np
import pandas as pd

HA_PER_KM2 = 100.0


# Spatial raster classification and RGB export removed as obsolete.
# YieldCalculator remains the single source for RUSLE tab calculations.


class YieldCalculator:
    def __init__(self):
        self.bulk_density = 1.3

    def calculate_usda_scs_sio(self, area_km2: float) -> float:
        if area_km2 <= 0:
            return 0.0
        return 0.51 * math.pow(area_km2, -0.11)

    def calculate_cem_sio(self, slope: float) -> float:
        """CEM SIO uses slope S as a decimal (m/m), not a percentage."""
        return 1.0 / (2.05823 + 0.02816 * math.pow(slope, 2))

    def calculate_average_sio(self, area_km2: float, slope: float) -> float:
        usda_sio = self.calculate_usda_scs_sio(area_km2)
        cem_sio = self.calculate_cem_sio(slope)
        return (usda_sio + cem_sio) / 2.0

    def raster_mean_t_ha_yr(self, raster_array: np.ndarray, nodata_value: float = -9999.0, basin_mask: np.ndarray = None) -> float:
        """
        Calculate the average erosion rate from a raster, ignoring NoData pixels and
        optional basin masking.
        """
        raster = np.asarray(raster_array, dtype=float)

        valid_pixels = np.isfinite(raster) & (raster != nodata_value)

        if basin_mask is not None:
            valid_pixels = valid_pixels & np.asarray(basin_mask, dtype=bool)

        basin_data = raster[valid_pixels]

        if basin_data.size == 0:
            return 0.0

        return float(np.mean(basin_data))

    def calculate_metrics(self, raster_mean_t_ha_yr: float, area_km2: float, slope: float):
        """Compute sediment metrics from a direct mean erosion-rate value in t/ha/yr."""
        if area_km2 <= 0:
            raise ValueError("Basin area must be greater than zero.")
        if raster_mean_t_ha_yr < 0:
            raise ValueError("Mean erosion rate must be non-negative.")
        if self.bulk_density <= 0:
            raise ValueError("Bulk density must be greater than zero.")

        area_ha = area_km2 * HA_PER_KM2
        gross_mass_t = raster_mean_t_ha_yr * area_ha

        usda_sio = self.calculate_usda_scs_sio(area_km2)
        cem_sio = self.calculate_cem_sio(slope)
        avg_sio = self.calculate_average_sio(area_km2, slope)

        yield_mass_t = gross_mass_t * avg_sio
        volume_m3 = yield_mass_t / self.bulk_density
        specific_yield = volume_m3 / area_km2

        return {
            "raster_mean_t_ha_yr": raster_mean_t_ha_yr,
            "area_ha": area_ha,
            "gross_mass_t": gross_mass_t,
            "usda_scs_sio": usda_sio,
            "cem_sio": cem_sio,
            "avg_sio": avg_sio,
            "yield_mass_t": yield_mass_t,
            "volume_m3": volume_m3,
            "specific_yield_m3_km2": specific_yield,
        }

    def to_phase2_handoff(self, year: int, volume_m3: float):
        return pd.DataFrame({"Year": [int(year)], "Suspended_Volume_m3": [float(volume_m3)]})