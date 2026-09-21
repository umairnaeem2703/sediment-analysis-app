import pandas as pd
import numpy as np

class IntegrationModule:
    def __init__(self):
        pass

    def merge_sediment_data(self, df_suspended: pd.DataFrame, df_bedload: pd.DataFrame) -> pd.DataFrame:
        if df_suspended.empty or df_bedload.empty:
            raise ValueError("One or both input dataframes are empty.")
        merged_df = pd.merge(df_suspended, df_bedload, on='Year', how='inner')
        merged_df['Total_Volume_m3'] = merged_df['Suspended_Volume_m3'] + merged_df['Bedload_Volume_m3']
        return merged_df

    def locate_extremes(self, merged_df: pd.DataFrame):
        if 'Total_Volume_m3' not in merged_df.columns:
            raise KeyError("Total_Volume_m3 column is missing from the dataset.")
        min_idx = merged_df['Total_Volume_m3'].idxmin()
        max_idx = merged_df['Total_Volume_m3'].idxmax()
        min_record = merged_df.loc[min_idx].to_dict()
        max_record = merged_df.loc[max_idx].to_dict()
        return min_record, max_record

    def interpolate_elevation(self, df_bathymetry: pd.DataFrame, target_volume: float) -> float:
        if df_bathymetry.empty:
            raise ValueError("Bathymetry dataframe is empty.")
        df_sorted = df_bathymetry.sort_values(by='Volume_m3')
        volumes = df_sorted['Volume_m3'].to_numpy()
        elevations = df_sorted['Elevation_m'].to_numpy()
        interpolated_elevation = np.interp(target_volume, volumes, elevations)
        return round(float(interpolated_elevation), 2)
        
    def generate_final_report_metrics(self, min_record: dict, max_record: dict, df_bathymetry: pd.DataFrame = None):
        if df_bathymetry is not None and not df_bathymetry.empty:
            min_record['Interpolated_Elevation_m'] = self.interpolate_elevation(df_bathymetry, min_record['Total_Volume_m3'])
            max_record['Interpolated_Elevation_m'] = self.interpolate_elevation(df_bathymetry, max_record['Total_Volume_m3'])
        return min_record, max_record