import pytest

from src.services.project import Project
from src.services.regional_data import RegionalData
from src.utils.paths import resource_path

HEADER = "Dam Name,Basin Name,Sub-basin Name,Drainage Area (km2),Main Waterway Slope"
SAMPLE_BASINS = resource_path("inputs", "master_yield.csv")


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


def test_c_m1_05_nothing_can_be_read_before_the_table_is_valid(project, data):
    dam = project.add_dam("A")

    with pytest.raises(ValueError, match="basin table"):
        data.sub_basins(dam)
