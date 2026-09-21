import numpy as np
import math

class SpatialProcessor:
    def __init__(self):
        self.bins_10_class = [1, 2, 4, 8, 16, 30, 60, 120, 300]
        self.bins_5_class = [1, 5, 10, 20] 
        self.colormap_5_class = {
            1: (255, 255, 128),
            2: (250, 209, 85), 
            3: (242, 167, 46),  
            4: (173, 83, 19),   
            5: (107, 0, 0)      
        }

    def classify_10_classes(self, raster_array: np.ndarray) -> np.ndarray:
        classified = np.digitize(raster_array, self.bins_10_class, right=True) + 1
        return np.clip(classified, 1, 10)

    def apply_5_class_colormap(self, raster_array: np.ndarray) -> np.ndarray:
        severity_class = np.digitize(raster_array, self.bins_5_class, right=True) + 1
        severity_class = np.clip(severity_class, 1, 5)
        
        rgb_raster = np.zeros((*raster_array.shape, 3), dtype=np.uint8)
        
        for severity_level, color in self.colormap_5_class.items():
            mask = (severity_class == severity_level)
            rgb_raster[mask] = color
            
        return rgb_raster

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

    def calculate_metrics(self, total_erosion: float, area_km2: float, slope: float):
        avg_sio = self.calculate_average_sio(area_km2, slope)
        mass = total_erosion * avg_sio
        volume = mass / self.bulk_density
        specific_yield = volume / area_km2 if area_km2 > 0 else 0.0
        return mass, volume, specific_yield