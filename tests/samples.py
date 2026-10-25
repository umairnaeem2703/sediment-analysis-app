"""The sample inputs in inputs/ loaded into a project, for tests that need the real three dams."""

from src.services.project import Project
from src.services.regional_data import RegionalData
from src.utils.paths import resource_path

SAMPLE_BASINS = resource_path("inputs", "master_yield.csv")
SAMPLE_ZONAL = resource_path("inputs", "raw_zonal_means.csv")


def sample_regional(folder) -> RegionalData:
    """A new project in `folder` holding the sample basin table and zonal means."""
    data = RegionalData(Project.new(folder, "Samples"))
    data.import_basin_table(SAMPLE_BASINS)
    data.import_zonal_means(SAMPLE_ZONAL)
    return data
