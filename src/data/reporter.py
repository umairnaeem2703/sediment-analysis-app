import logging
from typing import Sequence, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Matches FractionalModel.rho_s, used when the Wilcock export converts m³ to metric tons
SEDIMENT_DENSITY_KG_M3 = 2650.0


class IntegrationModule:
    def __init__(self):
        self.last_interpolation_warnings = []

    def merge_sediment_data(self, df_suspended: pd.DataFrame, df_bedload: pd.DataFrame):
        if df_suspended.empty or df_bedload.empty:
            raise ValueError("One or both input dataframes are empty.")

        candidates = ("Suspended_Volume_m3", "Volume_m3_yr", "Transported_Volume_m3_yr", "volume_m3_yr")
        vol_col = next((c for c in candidates if c in df_suspended.columns), None)
        if vol_col is None:
            raise KeyError("Phase 2 table missing columns: Suspended_Volume_m3 or Volume_m3_yr")
        # Sum sub-basin rows within a year, then average across years (if any)
        if "Year" in df_suspended.columns:
            suspended_val = float(df_suspended.groupby("Year")[vol_col].sum().mean())
        else:
            suspended_val = float(df_suspended[vol_col].sum())

        merged_df = df_bedload.copy()
        if "Bedload_Volume_m3" not in merged_df.columns:
            # Wilcock tab export: mass in metric tons/year -> volume via sediment density
            if "Annual Average Bed Load (metric tons/year)" in merged_df.columns:
                tons = merged_df["Annual Average Bed Load (metric tons/year)"].astype(float)
                merged_df["Bedload_Volume_m3"] = tons / (SEDIMENT_DENSITY_KG_M3 / 1000.0)
            elif "Annual_Total_Bedload_m3_yr" in merged_df.columns:
                merged_df["Bedload_Volume_m3"] = merged_df["Annual_Total_Bedload_m3_yr"].astype(float)
            else:
                raise KeyError("Phase 3 table missing columns: ['Bedload_Volume_m3']")

        merged_df["Suspended_Volume_m3"] = suspended_val
        merged_df["Total_Volume_m3"] = merged_df["Suspended_Volume_m3"] + merged_df["Bedload_Volume_m3"]

        return merged_df, None

    def locate_extremes(self, merged_df: pd.DataFrame, df_bathymetry: pd.DataFrame = None):
        if "Total_Volume_m3" not in merged_df.columns:
            raise KeyError("Total_Volume_m3 column is missing from the dataset.")
        if merged_df.empty:
            raise ValueError("Merged dataframe is empty.")
        min_idx = merged_df["Total_Volume_m3"].idxmin()
        max_idx = merged_df["Total_Volume_m3"].idxmax()
        min_record = merged_df.loc[min_idx].to_dict()
        max_record = merged_df.loc[max_idx].to_dict()

        if df_bathymetry is not None and not df_bathymetry.empty:
            self.generate_final_report_metrics(min_record, max_record, df_bathymetry)

        return min_record, max_record

    def prepare_bathymetry(self, df_bathymetry: pd.DataFrame):
        vol_col = "Volume m3" if "Volume m3" in df_bathymetry.columns else "Volume_m3"
        elev_col = "Elevation m" if "Elevation m" in df_bathymetry.columns else "Elevation_m"
        required = [vol_col, elev_col]
        missing = [col for col in required if col not in df_bathymetry.columns]
        if missing:
            raise KeyError(f"Bathymetry table missing columns: {missing}")
        if df_bathymetry.empty:
            raise ValueError("Bathymetry dataframe is empty.")
        df_sorted = df_bathymetry.dropna(subset=required).sort_values(by=vol_col)
        if df_sorted.empty:
            raise ValueError("Bathymetry dataframe has no valid volume/elevation rows.")
        if df_sorted[vol_col].duplicated().any():
            raise ValueError(f"Bathymetry {vol_col} values must be unique.")
        volumes = df_sorted[vol_col].to_numpy(dtype=float)
        elevations = df_sorted[elev_col].to_numpy(dtype=float)
        if not np.all(np.diff(volumes) > 0):
            raise ValueError(f"Bathymetry {vol_col} must be strictly increasing after sort.")
        return volumes, elevations

    def interpolate_elevations(self, volumes, elevations, targets):
        targets = np.asarray(targets, dtype=float)
        vmin, vmax = float(volumes[0]), float(volumes[-1])
        interpolated = np.interp(targets, volumes, elevations)
        warnings = []
        for target in targets:
            if target > vmax:
                msg = (
                    f"Warning: Calculated target volume {target:,.2f} m³ exceeds maximum bathymetric volume {vmax:,.2f} m³. "
                    "Elevation result was clamped to the maximum reservoir height."
                )
                warnings.append(msg)
                logger.warning(msg)
            elif target < vmin:
                msg = (
                    f"Warning: Calculated target volume {target:,.2f} m³ is below minimum bathymetric volume {vmin:,.2f} m³. "
                    "Elevation result was clamped."
                )
                warnings.append(msg)
                logger.warning(msg)
        return np.round(interpolated.astype(float), 2), warnings

    def interpolate_elevation(
        self,
        df_bathymetry: pd.DataFrame,
        target_volume: Union[float, Sequence[float], np.ndarray],
        return_warnings: bool = False,
    ):
        volumes, elevations = self.prepare_bathymetry(df_bathymetry)
        is_seq = isinstance(target_volume, (list, tuple, np.ndarray))
        targets = [float(v) for v in target_volume] if is_seq else [float(target_volume)]

        values, warnings = self.interpolate_elevations(volumes, elevations, targets)
        self.last_interpolation_warnings = warnings

        result = [float(v) for v in values] if is_seq else float(values[0])
        if return_warnings:
            return result, warnings
        return result

    def generate_final_report_metrics(self, min_record: dict, max_record: dict, df_bathymetry: pd.DataFrame = None):
        interp_warnings = []
        if df_bathymetry is not None and not df_bathymetry.empty:
            values, interp_warnings = self.interpolate_elevation(
                df_bathymetry,
                [min_record["Total_Volume_m3"], max_record["Total_Volume_m3"]],
                return_warnings=True,
            )
            min_record["Interpolated_Elevation_m"] = float(values[0])
            max_record["Interpolated_Elevation_m"] = float(values[1])
        return min_record, max_record, interp_warnings
