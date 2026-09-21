import pandas as pd
import pytest

from paths import read_table, resource_path
from reporter import IntegrationModule


def test_phase2_fixture_overlaps_flow_years_and_locate_extremes():
    p2 = read_table(resource_path("inputs", "phase2_suspended_yield.csv"))
    p3 = pd.DataFrame(
        {
            "Year": [2024, 2025],
            "Bedload_Volume_m3": [1000.0, 2500.0],
        }
    )
    module = IntegrationModule()
    merged, warning = module.merge_sediment_data(p2, p3)
    assert warning is None
    assert not merged.empty
    assert set(merged["Year"].tolist()) == {2024, 2025}
    min_record, max_record = module.locate_extremes(merged)
    assert int(min_record["Year"]) == 2024
    assert int(max_record["Year"]) == 2025


def test_inner_join_warns_on_dropped_years():
    p2 = pd.DataFrame({"Year": [2000, 2001], "Suspended_Volume_m3": [10.0, 20.0]})
    p3 = pd.DataFrame({"Year": [2001, 2002], "Bedload_Volume_m3": [1.0, 2.0]})
    merged, warning = IntegrationModule().merge_sediment_data(p2, p3)
    assert len(merged) == 1
    assert warning is not None
    assert "2000" in warning and "2002" in warning


def test_bathymetry_clamp_warning():
    bathy = read_table(resource_path("inputs", "bathymetry.csv"))
    module = IntegrationModule()
    volumes, elevations = module.prepare_bathymetry(bathy)
    values, warnings = module.interpolate_elevations(volumes, elevations, [0.0, 9_000_000.0])
    assert len(warnings) == 1 or len(warnings) == 2
    assert values[0] == elevations[0]
    assert values[1] == elevations[-1]


def test_duplicate_volumes_rejected():
    df = pd.DataFrame({"Volume_m3": [1.0, 1.0], "Elevation_m": [10.0, 11.0]})
    with pytest.raises(ValueError, match="unique"):
        IntegrationModule().prepare_bathymetry(df)
