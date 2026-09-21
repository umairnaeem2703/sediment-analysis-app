import pandas as pd
import os

class BasinDatabase:
    def __init__(self):
        self.data_dict = {}

    def load_from_dataframe(self, df: pd.DataFrame):
        self.data_dict = {}
        
        for _, row in df.iterrows():
            basin = row['Basin Name']
            subbasin = row['Sub-basin Name']
            
            if basin not in self.data_dict:
                self.data_dict[basin] = {}
                
            self.data_dict[basin][subbasin] = {
                'Area': row.get('Area', 0.0),
                'Slope': row.get('Main Waterway Slope', "") 
            }

    def load_from_excel(self, file_path: str):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The file {file_path} does not exist.")
            
        try:
            df = pd.read_excel(file_path)
            self.load_from_dataframe(df)
        except Exception as e:
            raise RuntimeError(f"Failed to read the Excel file: {e}")

    def get_area_and_slope(self, basin_name: str, subbasin_name: str):
        try:
            subbasin_data = self.data_dict[basin_name][subbasin_name]
            return subbasin_data['Area'], subbasin_data['Slope']
        except KeyError:
            return None, None