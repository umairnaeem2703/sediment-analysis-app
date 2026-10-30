import math
import unicodedata
from typing import Dict, List, NamedTuple, Optional, Set

import pandas as pd

HA_PER_KM2 = 100.0
_MIN_LOOSE_MATCH_LEN = 3

# Sub-basin name prefixes and suffixes (English & Turkish), tried in this order.
_NAME_PREFIXES = (
    "subbasin",
    "basin",
    "sub",
    "sb",
    "althavzasi",
    "althavzası",
    "althavza",
    "havzasi",
    "havzası",
    "havza",
)
_NAME_SUFFIXES = ("althavzasi", "althavzası", "althavza", "havzasi", "havzası", "havza", "subbasin", "basin")


class ZonalMatch(NamedTuple):
    """Result of ZonalMatcher.resolve_zonal_match; method is exact, loose, ambiguous or None."""

    value: Optional[float]
    method: Optional[str]
    candidates: List[str]


class ZonalResolution(NamedTuple):
    """Result of ZonalMatcher.resolve_all: per-name means, loose matches and unresolved names."""

    means: List[Optional[float]]
    loose: Dict[str, str]
    unresolved: List[str]


def turkish_lower(text: str) -> str:
    """Lowercase string using Turkish character rules (I -> ı, İ -> i)."""
    if text is None:
        return ""
    normalized = unicodedata.normalize("NFC", str(text))
    tr_map = {
        ord("I"): "ı",
        ord("İ"): "i",
    }
    return normalized.translate(tr_map).lower()


def to_ascii_turkish(text: str) -> str:
    """Convert Turkish characters to ASCII equivalents for robust matching."""
    if text is None:
        return ""
    ascii_map = {
        ord("ç"): "c",
        ord("Ç"): "C",
        ord("ğ"): "g",
        ord("Ğ"): "G",
        ord("ı"): "i",
        ord("I"): "I",
        ord("İ"): "I",
        ord("i"): "i",
        ord("ö"): "o",
        ord("Ö"): "O",
        ord("ş"): "s",
        ord("Ş"): "S",
        ord("ü"): "u",
        ord("Ü"): "U",
        ord("â"): "a",
        ord("Â"): "A",
        ord("î"): "i",
        ord("Î"): "I",
        ord("û"): "u",
        ord("Û"): "U",
    }
    return str(text).translate(ascii_map)


def name_key(text) -> str:
    """The comparison key of a dam or sub-basin name (D70): Turkish letters folded to ASCII, lowercase, and only
    letters and digits kept, so 'Çubuk 1', 'ÇUBUK-1' and 'cubuk1' give 'cubuk1'."""
    return "".join(ch for ch in to_ascii_turkish(turkish_lower(text)) if ch.isalnum())


class ZonalMatcher:
    """Handles subbasin name normalization, alias generation, and fuzzy lookup against zonal statistics."""

    @staticmethod
    def normalize_subbasin_name(value) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        lower = turkish_lower(text)
        try:
            numeric_value = float(lower)
        except ValueError:
            numeric_value = None

        if numeric_value is not None and math.isfinite(numeric_value):
            if numeric_value.is_integer():
                return str(int(numeric_value))
            return format(numeric_value, "g")

        normalized = "".join(ch for ch in lower if ch.isalnum())

        for prefix in _NAME_PREFIXES:
            if normalized.startswith(prefix):
                remainder = normalized[len(prefix) :]
                if remainder:
                    normalized = remainder
                    break

        for suffix in _NAME_SUFFIXES:
            if normalized.endswith(suffix):
                remainder = normalized[: -len(suffix)]
                if remainder:
                    normalized = remainder
                    break

        return normalized

    @classmethod
    def get_subbasin_aliases(cls, value) -> Set[str]:
        if value is None:
            return set()
        text = str(value).strip()
        if not text:
            return set()

        raw_tr = "".join(ch for ch in turkish_lower(text) if ch.isalnum())
        raw_ascii = to_ascii_turkish(raw_tr)
        key = cls.normalize_subbasin_name(value)
        key_ascii = to_ascii_turkish(key)

        aliases = {key, key_ascii, raw_tr, raw_ascii}
        if not key:
            return {a for a in aliases if a}

        for k in list(aliases):
            for pfx in _NAME_PREFIXES:
                if k.startswith(pfx) and len(k) > len(pfx):
                    aliases.add(k[len(pfx) :])
            for sfx in _NAME_SUFFIXES:
                if k.endswith(sfx) and len(k) > len(sfx):
                    aliases.add(k[: -len(sfx)])

        # Also add ascii versions of all aliases
        for k in list(aliases):
            aliases.add(to_ascii_turkish(k))

        return {alias for alias in aliases if alias}

    @classmethod
    def build_lookup(cls, names, means) -> Dict[str, float]:
        """Map every spelling of each sub-basin name to its zonal MEAN. `names` and `means` are the two columns of a
        validated zonal table; a name with no number is skipped."""
        lookup: Dict[str, float] = {}
        conflicting: Set[str] = set()
        for name, mean in zip(names, means, strict=True):
            if pd.isna(name) or str(name).strip() == "":
                continue
            mean_value = pd.to_numeric(mean, errors="coerce")
            if pd.isna(mean_value):
                continue

            float_mean = float(mean_value)
            for key in {cls.normalize_subbasin_name(name), *cls.get_subbasin_aliases(name)}:
                if key and lookup.setdefault(key, float_mean) != float_mean:
                    conflicting.add(key)

        if not lookup:
            raise ValueError("No valid sub-basin MEAN values were found in the zonal statistics file.")
        # A key that two entries claim with different values can not name either of them.
        for key in conflicting:
            del lookup[key]
        return lookup

    @classmethod
    def resolve_zonal_match(cls, zonal_lookup: Dict[str, float], subbasin_value) -> "ZonalMatch":
        """Resolve a sub-basin to its zonal MEAN.

        Exact and alias matches are returned directly. Looser matches (containment, or the same name with its number in
        another place) need the same number in both names and are accepted only when they point to a single value;
        ambiguous ones return value=None with the candidate keys so the caller can report them. A number shared by two
        otherwise different names is no match (D68).
        """
        if subbasin_value is None:
            return ZonalMatch(None, None, [])

        direct_key = cls.normalize_subbasin_name(subbasin_value)
        if direct_key in zonal_lookup:
            return ZonalMatch(zonal_lookup[direct_key], "exact", [direct_key])

        ascii_direct = to_ascii_turkish(direct_key)
        if ascii_direct in zonal_lookup:
            return ZonalMatch(zonal_lookup[ascii_direct], "exact", [ascii_direct])

        for alias in cls.get_subbasin_aliases(subbasin_value):
            if alias in zonal_lookup:
                return ZonalMatch(zonal_lookup[alias], "exact", [alias])

        digits_only = "".join(ch for ch in ascii_direct if ch.isdigit())
        ascii_len = len(ascii_direct)
        candidates: List[str] = []
        for candidate_key in zonal_lookup:
            cand_ascii = to_ascii_turkish(candidate_key)
            if not ascii_direct or not cand_ascii:
                continue
            if "".join(ch for ch in cand_ascii if ch.isdigit()) != digits_only:
                continue
            shorter, longer = sorted((ascii_direct, cand_ascii), key=len)
            if len(shorter) >= _MIN_LOOSE_MATCH_LEN and shorter in longer:
                candidates.append(candidate_key)
                continue
            if (
                digits_only
                and abs(len(cand_ascii) - ascii_len) <= 2
                and cand_ascii.replace(digits_only, "") == ascii_direct.replace(digits_only, "")
            ):
                candidates.append(candidate_key)

        if not candidates:
            return ZonalMatch(None, None, [])
        if len({zonal_lookup[k] for k in candidates}) > 1:
            return ZonalMatch(None, "ambiguous", sorted(candidates))
        return ZonalMatch(zonal_lookup[candidates[0]], "loose", sorted(candidates))

    @classmethod
    def resolve_all(cls, zonal_lookup: Dict[str, float], names) -> "ZonalResolution":
        """Resolve every sub-basin name; unmatched and ambiguous names are collected, not raised."""
        means: List[Optional[float]] = []
        loose: Dict[str, str] = {}
        unresolved: List[str] = []
        for name in names:
            match = cls.resolve_zonal_match(zonal_lookup, name)
            means.append(match.value)
            if match.value is None:
                if match.method == "ambiguous":
                    unresolved.append(f"{name} (ambiguous: {', '.join(match.candidates[:5])})")
                else:
                    unresolved.append(str(name))
            elif match.method == "loose":
                loose[str(name)] = match.candidates[0]
        return ZonalResolution(means, loose, unresolved)


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

        return {
            "raster_mean_t_ha_yr": raster_mean_t_ha_yr,
            "area_ha": area_ha,
            "gross_mass_t": gross_mass_t,
            "usda_scs_sio": usda_scs_sio,
            "cem_sio": cem_sio,
            "avg_sio": avg_sio,
            "yield_mass_t": yield_mass_t,
            "volume_m3": volume_m3,
            "specific_yield_m3_km2": specific_yield,
        }
