import pandas as pd

from paths import read_table, resource_path


class BasinDatabase:
    def __init__(self):
        self.data_dict = {}
        self.source_path = None

    def load_from_dataframe(self, df: pd.DataFrame):
        required = ["Basin Name", "Sub-basin Name"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise KeyError(f"Basin table missing columns: {missing}")

        self.data_dict = {}
        work = df.reset_index(drop=True)
        areas = pd.to_numeric(work.get("Area"), errors="coerce")
        slopes = pd.to_numeric(work.get("Main Waterway Slope"), errors="coerce")

        for idx, row in work.iterrows():
            basin = row["Basin Name"]
            subbasin = row["Sub-basin Name"]
            if pd.isna(basin) or pd.isna(subbasin):
                continue
            if basin not in self.data_dict:
                self.data_dict[basin] = {}

            area_val = areas.iloc[idx]
            slope_val = slopes.iloc[idx]
            self.data_dict[basin][subbasin] = {
                "Area": float(area_val) if pd.notna(area_val) else 0.0,
                "Slope": float(slope_val) if pd.notna(slope_val) else "",
            }

    def load_startup_basins(self):
        csv_path = resource_path("inputs", "TR_Basin_Subbasin_Area.csv")
        xlsx_path = resource_path("inputs", "TR_Basin_Subbasin_Area.xlsx")
        cwd_xlsx = resource_path("TR_Basin_Subbasin_Area.xlsx")

        for candidate in (csv_path, xlsx_path, cwd_xlsx):
            if candidate.exists():
                df = read_table(str(candidate))
                self.load_from_dataframe(df)
                self.source_path = str(candidate)
                return str(candidate)

        raise FileNotFoundError(
            "Basin table not found. Expected inputs/TR_Basin_Subbasin_Area.csv "
            "or a matching .xlsx next to the application."
        )

    def load_from_excel(self, file_path: str):
        df = read_table(file_path)
        self.load_from_dataframe(df)
        self.source_path = file_path

    def get_area_and_slope(self, basin_name: str, subbasin_name: str):
        try:
            subbasin_data = self.data_dict[basin_name][subbasin_name]
            return subbasin_data["Area"], subbasin_data["Slope"]
        except KeyError:
            return None, None
