import pandas as pd
import numpy as np


class IntegrationModule:
    def merge_sediment_data(self, df_suspended: pd.DataFrame, df_bedload: pd.DataFrame):
        if df_suspended.empty or df_bedload.empty:
            raise ValueError("One or both input dataframes are empty.")
        for name, df, cols in (
            ("Phase 2", df_suspended, ["Year", "Suspended_Volume_m3"]),
            ("Phase 3", df_bedload, ["Year", "Bedload_Volume_m3"]),
        ):
            missing = [col for col in cols if col not in df.columns]
            if missing:
                raise KeyError(f"{name} table missing columns: {missing}")

        left_years = set(df_suspended["Year"].tolist())
        right_years = set(df_bedload["Year"].tolist())
        dropped = sorted(left_years.symmetric_difference(right_years))
        merged_df = pd.merge(df_suspended, df_bedload, on="Year", how="inner")
        merged_df["Total_Volume_m3"] = merged_df["Suspended_Volume_m3"] + merged_df["Bedload_Volume_m3"]
        warning = None
        if dropped:
            warning = (
                f"Inner join dropped unmatched Year values: {dropped}. "
                f"{len(merged_df)} year(s) remain."
            )
        return merged_df, warning

    def locate_extremes(self, merged_df: pd.DataFrame):
        if "Total_Volume_m3" not in merged_df.columns:
            raise KeyError("Total_Volume_m3 column is missing from the dataset.")
        min_idx = merged_df["Total_Volume_m3"].idxmin()
        max_idx = merged_df["Total_Volume_m3"].idxmax()
        min_record = merged_df.loc[min_idx].to_dict()
        max_record = merged_df.loc[max_idx].to_dict()
        return min_record, max_record

    def prepare_bathymetry(self, df_bathymetry: pd.DataFrame):
        required = ["Volume_m3", "Elevation_m"]
        missing = [col for col in required if col not in df_bathymetry.columns]
        if missing:
            raise KeyError(f"Bathymetry table missing columns: {missing}")
        if df_bathymetry.empty:
            raise ValueError("Bathymetry dataframe is empty.")
        df_sorted = df_bathymetry.dropna(subset=required).sort_values(by="Volume_m3")
        if df_sorted.empty:
            raise ValueError("Bathymetry dataframe has no valid volume/elevation rows.")
        if df_sorted["Volume_m3"].duplicated().any():
            raise ValueError("Bathymetry Volume_m3 values must be unique.")
        volumes = df_sorted["Volume_m3"].to_numpy(dtype=float)
        elevations = df_sorted["Elevation_m"].to_numpy(dtype=float)
        if not np.all(np.diff(volumes) > 0):
            raise ValueError("Bathymetry Volume_m3 must be strictly increasing after sort.")
        return volumes, elevations

    def interpolate_elevations(self, volumes, elevations, targets):
        targets = np.asarray(targets, dtype=float)
        vmin, vmax = float(volumes[0]), float(volumes[-1])
        clamped = (targets < vmin) | (targets > vmax)
        interpolated = np.interp(targets, volumes, elevations)
        warnings = []
        for target, is_clamped in zip(targets, clamped):
            if is_clamped:
                warnings.append(
                    f"Volume {target:,.2f} m³ is outside [{vmin:,.2f}, {vmax:,.2f}] m³; elevation was clamped."
                )
        return np.round(interpolated.astype(float), 2), warnings

    def interpolate_elevation(self, df_bathymetry: pd.DataFrame, target_volume: float) -> float:
        volumes, elevations = self.prepare_bathymetry(df_bathymetry)
        values, _ = self.interpolate_elevations(volumes, elevations, [target_volume])
        return float(values[0])

    def generate_final_report_metrics(self, min_record: dict, max_record: dict, df_bathymetry: pd.DataFrame = None):
        interp_warnings = []
        if df_bathymetry is not None and not df_bathymetry.empty:
            volumes, elevations = self.prepare_bathymetry(df_bathymetry)
            values, interp_warnings = self.interpolate_elevations(
                volumes,
                elevations,
                [min_record["Total_Volume_m3"], max_record["Total_Volume_m3"]],
            )
            min_record["Interpolated_Elevation_m"] = float(values[0])
            max_record["Interpolated_Elevation_m"] = float(values[1])
        return min_record, max_record, interp_warnings
