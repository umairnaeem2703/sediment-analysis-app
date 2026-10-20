import pandas as pd

from src.core.rusle import find_basin_table_columns, to_ascii_turkish, turkish_lower
from src.utils.paths import read_table



class BasinDatabase:
    def __init__(self):
        self.data_dict = {}

    def load_from_dataframe(self, df: pd.DataFrame):
        col_map = find_basin_table_columns(df.columns)
        basin_col = col_map.get("basin")
        subbasin_col = col_map.get("subbasin")
        if not basin_col or not subbasin_col:
            required = ["Basin Name", "Sub-basin Name"]
            missing = [col for col in required if col not in df.columns]
            raise KeyError(f"Basin table missing columns: {missing or ['Basin Name', 'Sub-basin Name']}")

        area_col = col_map.get("area")
        slope_col = col_map.get("slope")

        self.data_dict = {}
        work = df.reset_index(drop=True)
        areas = pd.to_numeric(work[area_col], errors="coerce") if area_col else pd.Series(dtype=float)
        slopes = pd.to_numeric(work[slope_col], errors="coerce") if slope_col else pd.Series(dtype=float)

        for idx, row in work.iterrows():
            basin = row[basin_col]
            subbasin = row[subbasin_col]
            if pd.isna(basin) or pd.isna(subbasin):
                continue
            basin_str = str(basin).strip()
            subbasin_str = str(subbasin).strip()
            if not basin_str or not subbasin_str:
                continue

            if basin_str not in self.data_dict:
                self.data_dict[basin_str] = {}

            area_val = areas.iloc[idx] if idx < len(areas) else pd.NA
            slope_val = slopes.iloc[idx] if idx < len(slopes) else pd.NA
            self.data_dict[basin_str][subbasin_str] = {
                "Area": float(area_val) if pd.notna(area_val) else 0.0,
                "Slope": float(slope_val) if pd.notna(slope_val) else "",
            }


    def load_from_excel(self, file_path: str):
        df = read_table(file_path)
        self.load_from_dataframe(df)

    def get_area_and_slope(self, basin_name: str, subbasin_name: str):
        if basin_name in self.data_dict and subbasin_name in self.data_dict[basin_name]:
            subbasin_data = self.data_dict[basin_name][subbasin_name]
            return subbasin_data["Area"], subbasin_data["Slope"]

        # Case-insensitive / Turkish-normalized fallback lookup
        norm_b = turkish_lower(str(basin_name)).strip()
        norm_sb = turkish_lower(str(subbasin_name)).strip()
        ascii_b = to_ascii_turkish(norm_b)
        ascii_sb = to_ascii_turkish(norm_sb)

        for b_key, b_subdict in self.data_dict.items():
            b_norm = turkish_lower(str(b_key)).strip()
            if b_norm == norm_b or to_ascii_turkish(b_norm) == ascii_b:
                for sb_key, sb_data in b_subdict.items():
                    sb_norm = turkish_lower(str(sb_key)).strip()
                    if sb_norm == norm_sb or to_ascii_turkish(sb_norm) == ascii_sb:
                        return sb_data["Area"], sb_data["Slope"]
        return None, None

