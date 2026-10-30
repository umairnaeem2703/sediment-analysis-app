"""Suspended sediment of one dam (FR-M2-01 to FR-M2-04, B3.1).

The service takes the dam's own rows of the validated basin table and the zonal means, and refuses rows of more than
one dam, so a total can only ever hold that dam's sub-basins. `write_suspended_csv` writes `suspended.csv` into a
folder it is given; the run folder itself belongs to the reporting service (M5).
"""

from pathlib import Path
from typing import List, NamedTuple

import pandas as pd

from src.core.rusle import YieldCalculator, ZonalMatcher
from src.services.labels import MEAN
from src.services.regional import AREA, DAM, SLOPE, SUBBASIN, name_key

CSV_NAME = "suspended.csv"
TOTAL_LABEL = "Total"

# Output columns are named for their units (A7). The first three repeat the inputs so each row can be traced.
AREA_KM2, SLOPE_M_M, VOLUME_M3 = "Area_km2", "Slope_m_per_m", "Volume_m3"
_METRIC_COLUMNS = {
    "raster_mean_t_ha_yr": "Zonal_Mean_t_ha_yr",
    "gross_mass_t": "Gross_Mass_t",
    "usda_scs_sio": "SIO_USDA_SCS",
    "cem_sio": "SIO_CEM",
    "avg_sio": "SIO_Average",
    "yield_mass_t": "Yield_Mass_t",
    "volume_m3": VOLUME_M3,
    "specific_yield_m3_km2": "Specific_Yield_m3_km2",
}
OUTPUT_COLUMNS = [SUBBASIN, AREA_KM2, SLOPE_M_M, *_METRIC_COLUMNS.values()]
TOTAL_COLUMNS = [AREA_KM2, "Gross_Mass_t", "Yield_Mass_t", VOLUME_M3]


class SuspendedResult(NamedTuple):
    table: pd.DataFrame  # OUTPUT_COLUMNS, one row per sub-basin in the order of the basin table
    warnings: List[str]

    @property
    def totals(self) -> pd.Series:
        """The dam's totals over the columns that add up (TOTAL_COLUMNS)."""
        return self.table[TOTAL_COLUMNS].sum()

    @property
    def total_volume_m3(self) -> float:
        return float(self.totals[VOLUME_M3])


def _zonal_entry(zonal: pd.DataFrame, key: str) -> str:
    """The zonal file's own name for the lookup key a loose match ended on."""
    return next(name for name in zonal[SUBBASIN] if key in ZonalMatcher.get_subbasin_aliases(name))


def compute_suspended(
    sub_basins: pd.DataFrame, zonal: pd.DataFrame, zonal_source: str = "zonal means"
) -> SuspendedResult:
    """Suspended sediment of each sub-basin of one dam. `zonal_source` names the zonal file in error messages."""
    if sub_basins[DAM].map(name_key).nunique() > 1:
        raise ValueError(f"Suspended sediment is computed for one dam at a time; got {sorted(set(sub_basins[DAM]))}.")
    resolution = ZonalMatcher.resolve_all(
        ZonalMatcher.build_lookup(zonal[SUBBASIN], zonal[MEAN]), list(sub_basins[SUBBASIN])
    )
    if resolution.unresolved:
        raise ValueError(
            f"{zonal_source}: no zonal mean can be assigned to sub-basin(s): {', '.join(resolution.unresolved)}. "
            "Each sub-basin needs exactly one matching entry; names that appear twice with different values are not used."
        )
    calculator = YieldCalculator()
    rows = []
    for (_, basin), mean in zip(sub_basins.iterrows(), resolution.means, strict=True):
        try:
            metrics = calculator.calculate_metrics(mean, basin[AREA], basin[SLOPE])
        except ValueError as exc:
            raise ValueError(f"Sub-basin '{basin[SUBBASIN]}': {exc}") from exc
        rows.append(
            {
                SUBBASIN: basin[SUBBASIN],
                AREA_KM2: basin[AREA],
                SLOPE_M_M: basin[SLOPE],
                **{column: metrics[key] for key, column in _METRIC_COLUMNS.items()},
            }
        )
    warnings = [
        f"Sub-basin '{name}' was matched loosely to the zonal entry '{_zonal_entry(zonal, key)}'."
        for name, key in resolution.loose.items()
    ]
    return SuspendedResult(pd.DataFrame(rows, columns=OUTPUT_COLUMNS), warnings)


def table_with_total(result: SuspendedResult) -> pd.DataFrame:
    """The sub-basin rows and a final total row."""
    total = pd.DataFrame([{SUBBASIN: TOTAL_LABEL, **result.totals.to_dict()}])
    return pd.concat([result.table, total], ignore_index=True)


def write_suspended_csv(result: SuspendedResult, folder) -> Path:
    """Write the sub-basin rows and a final total row to `folder/suspended.csv` (UTF-8 with BOM, for Excel)."""
    path = Path(folder) / CSV_NAME
    table_with_total(result).to_csv(path, index=False, encoding="utf-8-sig")
    return path
