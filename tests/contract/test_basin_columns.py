import pytest

from src.core.rusle import find_basin_table_columns
from src.utils.paths import read_table, resource_path


def test_c_m1_03_master_yield_headers_are_all_recognised():
    df = read_table(resource_path("inputs", "master_yield.csv"))

    columns = find_basin_table_columns(df.columns)

    assert columns["dam"] == "Dam Name"
    assert columns["basin"] == "Basin Name"
    assert columns["subbasin"] == "Sub-basin Name"
    assert columns["area"] == "Drainage Area (km2)"
    assert columns["slope"] == "Main Waterway Slope"


@pytest.mark.parametrize("header", ["Drainage Area (km2)", "Drainage Area", "DRAINAGE AREA (KM2)"])
def test_c_m1_03_drainage_area_header_variants(header):
    assert find_basin_table_columns([header])["area"] == header
