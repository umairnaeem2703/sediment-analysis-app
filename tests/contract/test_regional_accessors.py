import pytest

from src.services.project import Project
from src.services.regional_data import RegionalData
from src.utils.paths import resource_path

HEADER = "Dam Name,Basin Name,Sub-basin Name,Drainage Area (km2),Main Waterway Slope"
SAMPLE_BASINS = resource_path("inputs", "master_yield.csv")
CUBUK_1_SHEET = resource_path("inputs", "bathymetry", "cubuk_1_bathymetry.csv")


@pytest.fixture()
def project(tmp_path):
    return Project.new(tmp_path / "project", "Region")


@pytest.fixture()
def data(project):
    return RegionalData(project)


def test_c_m1_05_a_dams_sub_basins_come_from_the_valid_table(tmp_path, project, data):
    path = tmp_path / "two.csv"
    path.write_bytes(
        (HEADER + "\nÇubuk 1,B,S1,100,0.1\nÇubuk 1,B,S2,300,0.3\nKavşakkaya,B,S1,50,0.2\n").encode("utf-8-sig")
    )
    data.import_basin_table(path)

    rows = data.sub_basins(project.dams[0])

    assert rows["Sub-basin Name"].tolist() == ["S1", "S2"]
    assert rows["Drainage Area (km2)"].tolist() == [100.0, 300.0]


def test_c_m1_05_a_dam_sheet_is_reread_from_the_project_copy(project, data):
    data.import_basin_table(SAMPLE_BASINS)
    data.import_dam_sheets([CUBUK_1_SHEET])

    loaded = data.dam_sheet(project.dams[1])

    assert loaded.data.name == "Çubuk 1" and loaded.data.max_vol_hm3 == 5.6
    assert loaded.warnings == []


def test_c_m1_05_a_dam_without_a_sheet_says_so(project, data):
    data.import_basin_table(SAMPLE_BASINS)

    with pytest.raises(ValueError, match="Kavşakkaya"):
        data.dam_sheet(project.dams[0])


def test_c_m1_06_the_sheet_is_cross_checked_against_the_current_table(project, data):
    data.import_basin_table(SAMPLE_BASINS)
    data.import_dam_sheets([CUBUK_1_SHEET])
    data.edit_cell(1, "Drainage Area (km2)", "999")

    assert any("drainage area" in w for w in data.dam_sheet(project.dams[1]).warnings)


def test_c_m1_05_nothing_can_be_read_before_the_table_is_valid(project, data):
    dam = project.add_dam("A")
    dam.sheet = "inputs/dams/a.csv"

    with pytest.raises(ValueError, match="basin table"):
        data.dam_sheet(dam)
    with pytest.raises(ValueError, match="basin table"):
        data.sub_basins(dam)
