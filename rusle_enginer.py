import math
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

HA_PER_KM2 = 100.0


class SpatialProcessor:
    def __init__(self):
        # Class 5 is strictly A > 20; 20.0 maps to class 4 with right=True (10 < A <= 20).
        self.bins_10_class = [1, 2, 4, 8, 16, 30, 60, 120, 300]
        self.bins_5_class = [1, 5, 10, 20]
        self.colormap_5_class = {
            1: (255, 255, 128),
            2: (250, 209, 85),
            3: (242, 167, 46),
            4: (173, 83, 19),
            5: (107, 0, 0),
        }
        self._lut_5 = np.array(
            [self.colormap_5_class[i] for i in range(1, 6)],
            dtype=np.uint8,
        )

    def _finite_raster(self, raster_array: np.ndarray) -> np.ndarray:
        raster = np.asarray(raster_array, dtype=float)
        return np.nan_to_num(raster, nan=0.0, posinf=0.0, neginf=0.0)

    def classify_10_classes(self, raster_array: np.ndarray) -> np.ndarray:
        classified = np.digitize(self._finite_raster(raster_array), self.bins_10_class, right=True) + 1
        return np.clip(classified, 1, 10)

    def classify_5_classes(self, raster_array: np.ndarray) -> np.ndarray:
        severity_class = np.digitize(self._finite_raster(raster_array), self.bins_5_class, right=True) + 1
        return np.clip(severity_class, 1, 5)

    def apply_5_class_colormap(self, raster_array: np.ndarray) -> np.ndarray:
        severity_class = self.classify_5_classes(raster_array)
        return self._lut_5[severity_class - 1]

    def export_rgb_tiff(self, rgb_raster: np.ndarray, file_path: str) -> None:
        """Write a non-georeferenced RGB TIFF or PNG via Pillow (no GDAL/rasterio)."""
        image = Image.fromarray(np.asarray(rgb_raster, dtype=np.uint8), mode="RGB")
        dest = Path(file_path)
        suffix = dest.suffix.lower()
        if suffix in {".tif", ".tiff"}:
            image.save(dest, format="TIFF")
        elif suffix == ".png":
            image.save(dest, format="PNG")
        else:
            image.save(dest.with_suffix(".tif"), format="TIFF")


class YieldCalculator:
    def __init__(self):
        self.bulk_density = 1.3

    def calculate_usda_scs_sio(self, area_km2: float) -> float:
        if area_km2 <= 0:
            return 0.0
        return 0.51 * math.pow(area_km2, -0.11)

    def calculate_cem_sio(self, slope: float) -> float:
        return 1.0 / (2.05823 + (0.02816 * math.pow(slope, 2)))

    def calculate_average_sio(self, area_km2: float, slope: float) -> float:
        usda_sio = self.calculate_usda_scs_sio(area_km2)
        cem_sio = self.calculate_cem_sio(slope)
        return (usda_sio + cem_sio) / 2.0

    def raster_mean_t_ha_yr(self, raster_array: np.ndarray) -> float:
        raster = np.asarray(raster_array, dtype=float)
        finite = raster[np.isfinite(raster)]
        if finite.size == 0:
            return 0.0
        return float(np.mean(finite))

    def calculate_metrics(self, raster_mean_t_ha_yr: float, area_km2: float, slope: float):
        """Gross mass = mean (t/ha/yr) * area_ha; yield mass applies average SIO."""
        if area_km2 <= 0:
            raise ValueError("Basin area must be greater than zero.")
        area_ha = area_km2 * HA_PER_KM2
        gross_mass_t = raster_mean_t_ha_yr * area_ha
        avg_sio = self.calculate_average_sio(area_km2, slope)
        yield_mass_t = gross_mass_t * avg_sio
        volume_m3 = yield_mass_t / self.bulk_density
        specific_yield = volume_m3 / area_km2
        return {
            "raster_mean_t_ha_yr": raster_mean_t_ha_yr,
            "area_ha": area_ha,
            "gross_mass_t": gross_mass_t,
            "avg_sio": avg_sio,
            "yield_mass_t": yield_mass_t,
            "volume_m3": volume_m3,
            "specific_yield_m3_km2": specific_yield,
        }

    def to_phase2_handoff(self, year: int, volume_m3: float):
        return pd.DataFrame({"Year": [int(year)], "Suspended_Volume_m3": [float(volume_m3)]})
