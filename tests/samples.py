"""The sample inputs in inputs/ loaded into a project, for tests that need the real three dams."""

from pathlib import Path

import pandas as pd

from src.core.monthly_flow_preprocessor import DEFAULT_SEED, DEFAULT_SIGMA
from src.core.wilcock import FractionalModel
from src.services.bedload import import_flow, import_fractions
from src.services.project import Project
from src.services.regional_data import RegionalData
from src.utils.paths import read_table, resource_path

SAMPLE_BASINS = resource_path("inputs", "master_yield.csv")
SAMPLE_ZONAL = resource_path("inputs", "raw_zonal_means.csv")
SAMPLE_FRACTIONS = resource_path("inputs", "fractional_parameters.csv")


def sample_regional(folder) -> RegionalData:
    """A new project in `folder` holding the sample basin table and zonal means."""
    data = RegionalData(Project.new(folder, "Samples"))
    data.import_basin_table(SAMPLE_BASINS)
    data.import_zonal_means(SAMPLE_ZONAL)
    return data


def sample_fraction_model() -> FractionalModel:
    """A Wilcock & Crowe model holding the sample grain fractions."""
    model = FractionalModel()
    model.load_fractional_parameters(read_table(SAMPLE_FRACTIONS))
    return model


def write_fractions_with_wrong_tau_ri(folder) -> Path:
    """The sample grain fractions with a tau_ri column 50% above the formula. The sample file itself agrees with the
    formula (D50) and gives no warning, so tests of the cross-check use this file, which warns for every fraction."""
    table = read_table(SAMPLE_FRACTIONS)
    wrong = pd.DataFrame({"di": table["di"], "Fi": table["Fi"], "tau_ri": pd.to_numeric(table["tau_ri"]) * 1.5})
    path = Path(folder) / "fractional_parameters.csv"
    wrong.to_csv(path, index=False)
    return path


def sample_flow(slug: str):
    """The DSİ monthly flow table of one of the three sample dams."""
    return resource_path("inputs", "dam_flow_data", f"{slug}_flow.csv")


def sample_bedload_inputs(folder) -> RegionalData:
    """`sample_regional` plus the sample grain fractions and each dam's DSİ flow table, split with the default sigma and seed."""
    data = sample_regional(folder)
    import_fractions(data.project, SAMPLE_FRACTIONS)
    for dam in data.project.dams:
        import_flow(data.project, dam, sample_flow(dam.slug), DEFAULT_SIGMA, DEFAULT_SEED)
    return data
