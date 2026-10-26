"""The sample inputs in inputs/ loaded into a project, for tests that need the real three dams."""

from pathlib import Path

import pandas as pd

from src.core.monthly_flow_preprocessor import DEFAULT_SEED, DEFAULT_SIGMA
from src.core.wilcock import FractionalModel
from src.services.bedload import compute_dam_bedload, import_flow, import_fractions
from src.services.integration import compute_dam_integration
from src.services.project import Project
from src.services.regional_data import RegionalData
from src.services.reservoir import compute_dam_curve
from src.services.suspended import compute_suspended
from src.utils.paths import read_table, resource_path

SAMPLE_BASINS = resource_path("inputs", "master_yield.csv")
SAMPLE_ZONAL = resource_path("inputs", "raw_zonal_means.csv")
SAMPLE_FRACTIONS = resource_path("inputs", "fractional_parameters.csv")
SAMPLE_SHAPE_CLASSES = {"kavsakkaya": "foothill", "cubuk_1": "hill", "cubuk_2": "hill"}
# Placeholders, not the dams' real years (OI-02): the integration goldens depend on them and are regenerated with the
# real years before they are signed off. The analysis year is fixed so that the goldens do not move with the date.
SAMPLE_COMMISSIONING_YEAR, SAMPLE_ANALYSIS_YEAR = 1990, 2020


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


def sample_sheet(slug: str):
    """The dam sheet of one of the three sample dams."""
    return resource_path("inputs", "bathymetry", f"{slug}_bathymetry.csv")


def _add_curves(data: RegionalData) -> RegionalData:
    """Each dam's sheet and the shape class of its worked example in B3.3 (no Hmin)."""
    data.import_dam_sheets([str(sample_sheet(dam.slug)) for dam in data.project.dams])
    for dam in data.project.dams:
        dam.shape_class = SAMPLE_SHAPE_CLASSES[dam.slug]
    data.project.save()
    return data


def sample_curve_inputs(folder) -> RegionalData:
    """`sample_regional` plus each dam's sheet and shape class."""
    return _add_curves(sample_regional(folder))


def sample_bedload_inputs(folder) -> RegionalData:
    """`sample_regional` plus the sample grain fractions and each dam's DSİ flow table, split with the default sigma and seed."""
    data = sample_regional(folder)
    import_fractions(data.project, SAMPLE_FRACTIONS)
    for dam in data.project.dams:
        import_flow(data.project, dam, sample_flow(dam.slug), DEFAULT_SIGMA, DEFAULT_SEED)
    return data


def sample_dam_results(data: RegionalData, slug: str):
    """The dam, then its suspended, bedload, curve and integration results, as steps 4 to 7 hold them."""
    dam = next(dam for dam in data.project.dams if dam.slug == slug)
    suspended = compute_suspended(data.sub_basins(dam), data.zonal)
    bedload = compute_dam_bedload(data.project, dam)
    curve = compute_dam_curve(data.dam_sheet(dam).data, dam)
    return dam, suspended, bedload, curve, compute_dam_integration(suspended, bedload, curve, dam)


def sample_integration_inputs(folder) -> RegionalData:
    """`sample_bedload_inputs` plus each dam's sheet and shape class, and the placeholder years of the three dams."""
    data = _add_curves(sample_bedload_inputs(folder))
    for dam in data.project.dams:
        dam.commissioning_year, dam.analysis_year = SAMPLE_COMMISSIONING_YEAR, SAMPLE_ANALYSIS_YEAR
    data.project.save()
    return data
