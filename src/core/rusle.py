import math
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd

HA_PER_KM2 = 100.0


@dataclass
class BasinRow:
    dam: str
    basin: str
    subbasin: str
    year: int
    area_km2: float
    slope: float


@dataclass
class RusleMetrics:
    raster_mean_t_ha_yr: float
    area_ha: float
    gross_mass_t: float
    usda_scs_sio: float
    cem_sio: float
    avg_sio: float
    yield_mass_t: float
    volume_m3: float
    specific_yield_m3_km2: float

    def to_dict(self) -> dict:
        return asdict(self)


class ZonalMatcher:
    """Handles subbasin name normalization, alias generation, and fuzzy lookup against zonal statistics."""

    @staticmethod
    def normalize_subbasin_name(value) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        lower = text.lower()
        try:
            numeric_value = float(lower)
        except ValueError:
            numeric_value = None

        if numeric_value is not None and math.isfinite(numeric_value):
            if numeric_value.is_integer():
                return str(int(numeric_value))
            return format(numeric_value, "g")

        normalized = "".join(ch for ch in lower if ch.isalnum())
        for prefix in ("subbasin", "basin", "sub", "sb"):
            if normalized.startswith(prefix):
                remainder = normalized[len(prefix):]
                if remainder:
                    return remainder
        return normalized

    @classmethod
    def get_subbasin_aliases(cls, value) -> Set[str]:
        key = cls.normalize_subbasin_name(value)
        aliases = {key}
        if not key:
            return aliases

        digits_only = "".join(ch for ch in key if ch.isdigit())
        if digits_only:
            aliases.add(digits_only)

        if key.startswith("subbasin"):
            aliases.add(key[len("subbasin"):])
        if key.startswith("basin"):
            aliases.add(key[len("basin"):])
        if key.startswith("sub") and len(key) > 3:
            aliases.add(key[3:])
        return {alias for alias in aliases if alias}

    @classmethod
    def build_lookup(cls, zonal_df: pd.DataFrame) -> Dict[str, float]:
        if zonal_df.empty:
            raise ValueError("The selected zonal statistics file is empty.")

        mean_cols = [col for col in ("MEAN", "mean") if col in zonal_df.columns]
        if not mean_cols:
            raise ValueError("Zonal statistics file must contain a MEAN column.")
        mean_col = mean_cols[0]

        name_col = None
        for candidate in zonal_df.columns:
            normalized = candidate.strip().lower()
            if "sub" in normalized and "basin" in normalized:
                name_col = candidate
                break
        if name_col is None:
            for candidate in zonal_df.columns:
                normalized = candidate.strip().lower()
                if "basin" in normalized:
                    name_col = candidate
                    break
        if name_col is None:
            raise ValueError("Zonal statistics file must include a sub-basin name column.")

        lookup: Dict[str, float] = {}
        for _, row in zonal_df.iterrows():
            name = row.get(name_col)
            if pd.isna(name) or str(name).strip() == "":
                continue
            mean_value = pd.to_numeric(row.get(mean_col), errors="coerce")
            if pd.isna(mean_value):
                continue

            normalized_name = cls.normalize_subbasin_name(name)
            if not normalized_name:
                continue

            float_mean = float(mean_value)
            lookup[normalized_name] = float_mean
            for alias in cls.get_subbasin_aliases(name):
                if alias:
                    lookup[alias] = float_mean

        if not lookup:
            raise ValueError("No valid sub-basin MEAN values were found in the zonal statistics file.")
        return lookup

    @classmethod
    def resolve_zonal_mean(cls, zonal_lookup: Dict[str, float], subbasin_value) -> Optional[float]:
        if subbasin_value is None:
            return None

        direct_key = cls.normalize_subbasin_name(subbasin_value)
        if direct_key in zonal_lookup:
            return zonal_lookup[direct_key]

        for alias in cls.get_subbasin_aliases(subbasin_value):
            if alias in zonal_lookup:
                return zonal_lookup[alias]

        digits_only = "".join(ch for ch in direct_key if ch.isdigit())
        if digits_only:
            for candidate_key, value in zonal_lookup.items():
                candidate_digits = "".join(ch for ch in candidate_key if ch.isdigit())
                if candidate_digits == digits_only:
                    return value

        direct_key_len = len(direct_key)
        for candidate_key, value in zonal_lookup.items():
            if candidate_key == direct_key:
                return value
            if direct_key and candidate_key and (candidate_key.endswith(direct_key) or direct_key.endswith(candidate_key)):
                return value
            if direct_key and candidate_key and (direct_key in candidate_key or candidate_key in direct_key):
                return value
            if (
                direct_key
                and candidate_key
                and abs(len(candidate_key) - direct_key_len) <= 2
                and candidate_key.replace(digits_only, "") == direct_key.replace(digits_only, "")
            ):
                return value

        return None


class YieldCalculator:
    def __init__(self, bulk_density: float = 1.3):
        self.bulk_density = bulk_density

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
        """Calculate the average erosion rate from a raster array."""
        raster = np.asarray(raster_array, dtype=float)
        valid_pixels = np.isfinite(raster) & (raster != nodata_value)

        if basin_mask is not None:
            valid_pixels = valid_pixels & np.asarray(basin_mask, dtype=bool)

        basin_data = raster[valid_pixels]
        if basin_data.size == 0:
            return 0.0

        return float(np.mean(basin_data))

    def calculate_metrics(self, raster_mean_t_ha_yr: float, area_km2: float, slope: float) -> dict:
        """Compute sediment metrics from a direct mean erosion-rate value in t/ha/yr."""
        if area_km2 <= 0:
            raise ValueError("Basin area must be greater than zero.")
        if raster_mean_t_ha_yr < 0:
            raise ValueError("Mean erosion rate must be non-negative.")
        if self.bulk_density <= 0:
            raise ValueError("Bulk density must be greater than zero.")

        area_ha = area_km2 * HA_PER_KM2
        gross_mass_t = raster_mean_t_ha_yr * area_ha

        usda_scs_sio = self.calculate_usda_scs_sio(area_km2)
        cem_sio = self.calculate_cem_sio(slope)
        avg_sio = self.calculate_average_sio(area_km2, slope)

        yield_mass_t = gross_mass_t * avg_sio
        volume_m3 = yield_mass_t / self.bulk_density
        specific_yield = volume_m3 / area_km2

        return RusleMetrics(
            raster_mean_t_ha_yr=raster_mean_t_ha_yr,
            area_ha=area_ha,
            gross_mass_t=gross_mass_t,
            usda_scs_sio=usda_scs_sio,
            cem_sio=cem_sio,
            avg_sio=avg_sio,
            yield_mass_t=yield_mass_t,
            volume_m3=volume_m3,
            specific_yield_m3_km2=specific_yield,
        ).to_dict()

    def to_phase2_handoff(self, year: int, volume_m3: float) -> pd.DataFrame:
        return pd.DataFrame({"Year": [int(year)], "Suspended_Volume_m3": [float(volume_m3)]})
