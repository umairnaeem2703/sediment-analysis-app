import hashlib
import json

import pandas as pd
import pytest

from src.services.project import Project
from src.services.regional import Problem, TableError, read_basin_grid, validate_basin_table
from src.services.regional_data import RegionalData
from src.utils.paths import resource_path

HEADER = "Dam Name,Basin Name,Sub-basin Name,Drainage Area (km2),Main Waterway Slope"
SAMPLE_BASINS = resource_path("inputs", "master_yield.csv")
SAMPLE_ZONAL = resource_path("inputs", "raw_zonal_means.csv")
SAMPLE_SHEETS = {
    slug: resource_path("inputs", "bathymetry", f"{slug}_bathymetry.csv")
    for slug in ("kavsakkaya", "cubuk_1", "cubuk_2")
}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _csv(tmp_path, name, *rows, header=HEADER):
    path = tmp_path / name
    path.write_bytes(("\n".join([header, *rows]) + "\n").encode("utf-8-sig"))
    return path


@pytest.fixture()
def project(tmp_path):
    return Project.new(tmp_path / "project", "Region")


@pytest.fixture()
def data(project):
    return RegionalData(project)


# --- structured problems ----------------------------------------------------------------------


def test_c_m1_04_table_errors_locate_the_invalid_cells():
    grid = pd.DataFrame(
        {
            "Dam Name": ["A", "A", "B"],
            "Basin Name": ["x", "x", "x"],
            "Sub-basin Name": ["S1", "s1", "S1"],
            "Drainage Area (km2)": ["10", "0", "abc"],
            "Main Waterway Slope": ["0.1", "0.2", ""],
        }
    )

    with pytest.raises(TableError) as error:
        validate_basin_table(grid, "grid")

    cells = {cell for problem in error.value.problems for cell in problem.cells}
    assert cells == {
        (3, "Drainage Area (km2)"),
        (4, "Drainage Area (km2)"),
        (4, "Main Waterway Slope"),
        (2, "Sub-basin Name"),
        (3, "Sub-basin Name"),
    }
    assert all(isinstance(problem, Problem) for problem in error.value.problems)
    assert isinstance(error.value, ValueError)
    assert "grid: 4 problem(s) found" in str(error.value)


def test_c_m1_08_read_basin_grid_keeps_cell_text_under_canonical_headers(tmp_path):
    path = _csv(
        tmp_path,
        "t.csv",
        "A,B,S1,10.50,steep",
        ",,,,",
        header="DAM NAME,basin name,Sub-basin  Name,Drainage Area (km²),main waterway slope",
    )

    grid = read_basin_grid(path).data

    assert list(grid.columns) == HEADER.split(",")
    assert grid.loc[0].tolist() == ["A", "B", "S1", "10.50", "steep"]  # text exactly as written
    assert grid.loc[1].tolist() == ["", "", "", "", ""]


def test_c_m1_08_read_basin_grid_rejects_missing_columns(tmp_path):
    path = _csv(tmp_path, "t.csv", "A,B,S1", header="Dam Name,Basin Name,Sub-basin Name")

    with pytest.raises(ValueError, match=r"required column.*Drainage Area"):
        read_basin_grid(path)


# --- basin table import (FR-M1-02, FR-M1-04) ---------------------------------------------------


def test_c_m1_02_importing_the_sample_table_copies_it_and_creates_the_dams(project, data):
    before = _sha(SAMPLE_BASINS)

    notices = data.import_basin_table(SAMPLE_BASINS)

    copy = project.folder / project.inputs["basins"]
    assert project.inputs["basins"] == "inputs/basins.csv"
    assert _sha(copy) == before == _sha(SAMPLE_BASINS)
    assert data.problems == [] and data.basin_table is not None
    assert [(d.name, d.slug) for d in project.dams] == [
        ("Kavşakkaya", "kavsakkaya"),
        ("Çubuk 1", "cubuk_1"),
        ("Çubuk 2", "cubuk_2"),
    ]
    assert notices == []
    saved = json.loads((project.folder / "project.json").read_text(encoding="utf-8"))
    assert saved["inputs"]["basins"] == "inputs/basins.csv"
    assert [d["slug"] for d in saved["dams"]] == ["kavsakkaya", "cubuk_1", "cubuk_2"]


def test_c_m1_04_a_table_with_invalid_cells_is_still_copied_and_flagged(tmp_path, project, data):
    path = _csv(tmp_path, "bad.csv", "A,B,S1,10,0.1", "A,B,S2,-1,0.2")

    data.import_basin_table(path)

    assert (project.folder / "inputs" / "basins.csv").is_file()
    assert data.basin_table is None
    assert [cell for problem in data.problems for cell in problem.cells] == [(3, "Drainage Area (km2)")]
    assert data.grid.loc[1, "Drainage Area (km2)"] == "-1"
    assert project.dams == []
    assert not data.complete


def test_c_m1_04_a_table_missing_required_columns_is_rejected_and_nothing_is_copied(tmp_path, project, data):
    path = _csv(tmp_path, "bad.csv", "A,B,S1", header="Dam Name,Basin Name,Sub-basin Name")

    with pytest.raises(ValueError, match="required column"):
        data.import_basin_table(path)

    assert project.inputs["basins"] is None
    assert not (project.folder / "inputs" / "basins.csv").exists()
    assert data.grid is None


def test_c_m1_08_editing_a_cell_rewrites_the_copy_and_revalidates(tmp_path, project, data):
    original = _csv(tmp_path, "bad.csv", "A,B,S1,10,0.1", "A,B,S2,-1,0.2")
    original_sha = _sha(original)
    data.import_basin_table(original)

    data.edit_cell(1, "Drainage Area (km2)", " 25 ")

    assert data.problems == []
    assert data.basin_table["Drainage Area (km2)"].tolist() == [10.0, 25.0]
    assert [d.slug for d in project.dams] == ["a"]
    copy = project.folder / "inputs" / "basins.csv"
    assert copy.read_bytes().startswith(b"\xef\xbb\xbf" + HEADER.encode("utf-8"))
    assert pd.read_csv(copy, encoding="utf-8-sig").loc[1, "Drainage Area (km2)"] == 25
    assert _sha(original) == original_sha  # the file the user picked is never touched


def test_c_m1_08_an_edit_can_make_a_valid_table_invalid_again(project, data):
    data.import_basin_table(SAMPLE_BASINS)

    data.edit_cell(0, "Drainage Area (km2)", "oops")

    assert data.basin_table is None
    assert [cell for problem in data.problems for cell in problem.cells] == [(2, "Drainage Area (km2)")]
    assert len(project.dams) == 3  # dams are only synced from a valid table


def test_c_m1_08_unknown_columns_are_refused(data):
    data.import_basin_table(SAMPLE_BASINS)

    with pytest.raises(ValueError, match="Nope"):
        data.edit_cell(0, "Nope", "x")


def test_c_m1_08_an_excel_original_is_replaced_by_a_csv_copy_on_the_first_edit(tmp_path, project, data):
    workbook = tmp_path / "basins.xlsx"
    pd.read_csv(SAMPLE_BASINS, encoding="utf-8-sig").to_excel(workbook, index=False)
    data.import_basin_table(workbook)
    assert project.inputs["basins"] == "inputs/basins.xlsx"

    data.edit_cell(0, "Main Waterway Slope", "0.24")

    assert project.inputs["basins"] == "inputs/basins.csv"
    assert not (project.folder / "inputs" / "basins.xlsx").exists()
    assert data.basin_table["Main Waterway Slope"].tolist()[0] == 0.24


# --- dams follow the table (Q2) ---------------------------------------------------------------


def test_c_m1_04_dam_settings_survive_a_new_table_and_vanished_dams_are_reported(tmp_path, project, data):
    data.import_basin_table(SAMPLE_BASINS)
    project.dams[1].commissioning_year = 1965
    project.dams[1].trap_efficiency_pct = 80.0

    shorter = _csv(
        tmp_path,
        "two.csv",
        "ÇUBUK 1,Sakarya,Ankara Alt Havzası,834.7,0.09",
        "Sariyar,Sakarya,Ankara Alt Havzası,100,0.1",
    )
    notices = data.import_basin_table(shorter)

    assert [d.slug for d in project.dams] == ["cubuk_1", "sariyar"]
    assert project.dams[0].commissioning_year == 1965 and project.dams[0].trap_efficiency_pct == 80.0
    assert project.dams[0].name == "ÇUBUK 1"
    assert len(notices) == 1
    assert "Kavşakkaya" in notices[0] and "Çubuk 2" in notices[0]
    assert "removed" in notices[0]


def test_c_m1_04_spellings_of_one_dam_name_are_one_dam_named_by_the_first(tmp_path, project, data):
    path = _csv(tmp_path, "t.csv", "Çubuk 1,B,S1,10,0.1", "Cubuk-1,B,S2,20,0.2", "CUBUK1,B,S3,30,0.3")

    data.import_basin_table(path)

    assert data.problems == []
    assert [(dam.name, dam.slug) for dam in project.dams] == [("Çubuk 1", "cubuk_1")]
    assert list(data.sub_basins(project.dams[0])["Sub-basin Name"]) == ["S1", "S2", "S3"]


def test_c_m1_04_dams_whose_names_differ_only_in_a_number_with_a_dot_stay_two_dams(tmp_path, project, data):
    path = _csv(tmp_path, "t.csv", "Baraj 1.1,B,S1,10,0.1", "Baraj 11,B,S1,20,0.2")

    data.import_basin_table(path)

    assert data.problems == []
    assert [dam.name for dam in project.dams] == ["Baraj 1.1", "Baraj 11"]
    assert [len(data.sub_basins(dam)) for dam in project.dams] == [1, 1]


def test_c_m1_04_two_names_the_key_tells_apart_but_the_identifier_does_not_are_a_flagged_problem(
    tmp_path, project, data
):
    path = _csv(tmp_path, "t.csv", "Café,B,S1,10,0.1", ",,,,", "Caf,B,S1,20,0.2")

    data.import_basin_table(path)

    assert data.basin_table is None and project.dams == []
    assert any("same identifier 'caf'" in problem.message for problem in data.problems)
    assert {cell for problem in data.problems for cell in problem.cells} == {(2, "Dam Name"), (4, "Dam Name")}


def test_c_m1_04_a_respelled_dam_keeps_its_settings_its_slug_and_takes_its_sheet(tmp_path, project, data):
    data.import_basin_table(_csv(tmp_path, "t.csv", "Çubuk 1,B,Ankara Alt Havzası,834.7,0.09"))
    dam = project.dams[0]
    dam.commissioning_year, dam.trap_efficiency_pct = 1965, 87.0
    project.save()

    notices = data.import_basin_table(_csv(tmp_path, "u.csv", "Çubuk1,B,Ankara Alt Havzası,834.7,0.09"))

    assert notices == [] and project.dams == [dam]
    assert (dam.name, dam.slug, dam.commissioning_year, dam.trap_efficiency_pct) == ("Çubuk1", "cubuk_1", 1965, 87.0)
    assert data.import_dam_sheets([SAMPLE_SHEETS["cubuk_1"]]).errors == []
    assert dam.sheet == "inputs/dams/cubuk_1.csv"


# --- zonal means (FR-M1-06) --------------------------------------------------------------------


def test_c_m1_07_zonal_means_are_validated_then_copied(project, data):
    before = _sha(SAMPLE_ZONAL)

    warnings = data.import_zonal_means(SAMPLE_ZONAL)

    assert warnings == []
    assert project.inputs["zonal_means"] == "inputs/zonal_means.csv"
    assert _sha(project.folder / "inputs" / "zonal_means.csv") == before
    assert len(data.zonal) == 6


def test_c_m1_07_skipped_zonal_rows_come_back_as_warnings(tmp_path, data):
    path = tmp_path / "z.csv"
    path.write_text("Sub-basin Name,MEAN\nA,1.5\nB,\n", encoding="utf-8")

    warnings = data.import_zonal_means(path)

    assert "skipped 1 row(s)" in warnings[0]
    assert data.zonal_warnings == warnings


def test_c_m1_07_an_unusable_zonal_file_is_rejected_and_nothing_is_copied(tmp_path, project, data):
    path = tmp_path / "z.csv"
    path.write_text("Sub-basin Name,Value\nA,1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="MEAN"):
        data.import_zonal_means(path)

    assert project.inputs["zonal_means"] is None
    assert data.zonal is None


def test_c_m1_04_the_regional_step_is_complete_with_a_valid_table_and_zonal_means(data):
    assert not data.complete
    data.import_basin_table(SAMPLE_BASINS)
    assert not data.complete
    data.import_zonal_means(SAMPLE_ZONAL)
    assert data.complete


# --- dam sheets (FR-M1-05) ---------------------------------------------------------------------


def test_c_m1_05_sheets_are_matched_by_dam_name_and_copied_per_dam(project, data):
    data.import_basin_table(SAMPLE_BASINS)
    before = {slug: _sha(path) for slug, path in SAMPLE_SHEETS.items()}

    result = data.import_dam_sheets(list(SAMPLE_SHEETS.values()))

    assert result.errors == [] and result.warnings == []
    assert sorted(result.imported) == ["Kavşakkaya", "Çubuk 1", "Çubuk 2"]
    by_slug = {d.slug: d for d in project.dams}
    for slug in SAMPLE_SHEETS:
        assert by_slug[slug].sheet == f"inputs/dams/{slug}.csv"
        assert _sha(project.folder / by_slug[slug].sheet) == before[slug]
    saved = json.loads((project.folder / "project.json").read_text(encoding="utf-8"))
    assert all(d["sheet"] for d in saved["dams"])


def test_c_m1_05_a_bad_sheet_does_not_stop_the_others(tmp_path, project, data):
    data.import_basin_table(SAMPLE_BASINS)
    stranger = tmp_path / "stranger.csv"
    stranger.write_text(
        SAMPLE_SHEETS["cubuk_1"].read_text(encoding="utf-8-sig").replace("Çubuk 1", "Sariyar"), encoding="utf-8-sig"
    )

    result = data.import_dam_sheets([stranger, SAMPLE_SHEETS["cubuk_1"], tmp_path / "missing.csv"])

    assert result.imported == ["Çubuk 1"]
    assert len(result.errors) == 2
    assert "Sariyar" in result.errors[0] and "stranger.csv" in result.errors[0]
    assert "missing.csv" in result.errors[1]
    assert [d.sheet for d in project.dams] == [None, "inputs/dams/cubuk_1.csv", None]


def test_c_m1_05_sheet_cross_check_warnings_are_returned(tmp_path, data):
    data.import_basin_table(SAMPLE_BASINS)
    off = tmp_path / "off.csv"
    off.write_text(
        SAMPLE_SHEETS["cubuk_1"].read_text(encoding="utf-8-sig").replace("834.7", "999"), encoding="utf-8-sig"
    )

    result = data.import_dam_sheets([off])

    assert result.imported == ["Çubuk 1"]
    assert any("drainage area" in w for w in result.warnings)


def test_c_m1_05_sheets_need_a_valid_basin_table_first(data):
    with pytest.raises(ValueError, match="basin table"):
        data.import_dam_sheets(list(SAMPLE_SHEETS.values()))


# --- reopening the project ---------------------------------------------------------------------


def test_c_m1_01_a_reopened_project_restores_the_regional_state(tmp_path, project, data):
    data.import_basin_table(SAMPLE_BASINS)
    data.import_zonal_means(SAMPLE_ZONAL)
    data.edit_cell(0, "Main Waterway Slope", "0.25")

    again = RegionalData(Project.open(project.folder))

    assert again.load_errors == []
    assert again.complete
    pd.testing.assert_frame_equal(again.grid, data.grid)
    pd.testing.assert_frame_equal(again.basin_table, data.basin_table)
    pd.testing.assert_frame_equal(again.zonal, data.zonal)


def test_c_m1_01_a_reopened_invalid_table_is_still_flagged(tmp_path, project, data):
    data.import_basin_table(_csv(tmp_path, "bad.csv", "A,B,S1,0,0.1"))

    again = RegionalData(Project.open(project.folder))

    assert again.basin_table is None
    assert [cell for problem in again.problems for cell in problem.cells] == [(2, "Drainage Area (km2)")]


def test_c_x_01_a_missing_project_copy_is_reported_not_raised(project, data):
    data.import_basin_table(SAMPLE_BASINS)
    data.import_zonal_means(SAMPLE_ZONAL)
    (project.folder / "inputs" / "basins.csv").unlink()

    again = RegionalData(Project.open(project.folder))

    assert again.grid is None and not again.complete
    assert len(again.load_errors) == 1
    assert "basins.csv" in again.load_errors[0]


# --- edge cases found while writing the service -------------------------------------------------


def test_c_m1_04_a_dam_name_that_cannot_make_an_identifier_is_a_flagged_problem(tmp_path, project, data):
    data.import_basin_table(_csv(tmp_path, "t.csv", "???,B,S1,10,0.1"))

    assert data.basin_table is None
    assert [cell for problem in data.problems for cell in problem.cells] == [(2, "Dam Name")]
    assert "identifier" in data.problems[0].message


def test_c_m1_04_a_table_with_no_data_rows_is_refused_and_nothing_is_copied(tmp_path, project, data):
    with pytest.raises(ValueError, match="no data rows"):
        data.import_basin_table(_csv(tmp_path, "empty.csv", ",,,,"))

    assert project.inputs["basins"] is None
    assert not (project.folder / "inputs" / "basins.csv").exists()


def test_c_m1_08_blanking_every_cell_is_reported_as_a_problem_not_raised(tmp_path, project, data):
    data.import_basin_table(_csv(tmp_path, "one.csv", "A,B,S1,10,0.1"))

    for column in ("Dam Name", "Basin Name", "Sub-basin Name", "Drainage Area (km2)", "Main Waterway Slope"):
        data.edit_cell(0, column, "")

    assert data.basin_table is None
    assert "no data rows" in data.problems[0].message


# --- review follow-ups -------------------------------------------------------------------------


def test_c_m1_08_the_grid_keeps_leading_zeros_in_names(tmp_path, data):
    data.import_basin_table(_csv(tmp_path, "t.csv", "007,B,01,10,0.1"))

    assert data.grid.loc[0, "Dam Name"] == "007"
    assert data.grid.loc[0, "Sub-basin Name"] == "01"


def test_c_m1_04_a_sub_basin_listed_twice_with_other_spacing_is_flagged_at_both_grid_rows(tmp_path, project, data):
    path = _csv(tmp_path, "t.csv", "Dam,B,Dere 1,10,0.1", ",,,,", "Dam,B,DERE-1,20,0.2")

    data.import_basin_table(path)

    assert {cell for problem in data.problems for cell in problem.cells} == {
        (2, "Sub-basin Name"),
        (4, "Sub-basin Name"),
    }


@pytest.mark.parametrize("position", [-1, 1, 99])
def test_c_m1_08_editing_outside_the_grid_is_an_error(tmp_path, project, data, position):
    data.import_basin_table(_csv(tmp_path, "t.csv", "A,B,S1,10,0.1"))
    before = data.grid.copy()

    with pytest.raises(ValueError, match="row"):
        data.edit_cell(position, "Dam Name", "X")

    pd.testing.assert_frame_equal(data.grid, before)


def test_c_m1_08_editing_without_a_basin_table_is_an_error(data):
    with pytest.raises(ValueError, match="basin table"):
        data.edit_cell(0, "Dam Name", "X")


def test_c_m1_08_a_failed_write_leaves_the_grid_and_the_project_unchanged(tmp_path, project, data, monkeypatch):
    data.import_basin_table(SAMPLE_BASINS)
    before = data.grid.copy()
    copy_before = (project.folder / "inputs" / "basins.csv").read_bytes()

    def locked(self, *args, **kwargs):
        raise PermissionError("file is open in another program")

    monkeypatch.setattr(pd.DataFrame, "to_csv", locked)
    with pytest.raises(PermissionError):
        data.edit_cell(0, "Main Waterway Slope", "0.99")

    pd.testing.assert_frame_equal(data.grid, before)
    assert (project.folder / "inputs" / "basins.csv").read_bytes() == copy_before
    assert data.basin_table is not None


def test_c_m1_07_a_zonal_file_with_another_extension_replaces_the_old_copy(tmp_path, project, data):
    workbook = tmp_path / "zonal.xlsx"
    pd.read_csv(SAMPLE_ZONAL, encoding="utf-8-sig").to_excel(workbook, index=False)
    data.import_zonal_means(workbook)
    assert project.inputs["zonal_means"] == "inputs/zonal_means.xlsx"

    data.import_zonal_means(SAMPLE_ZONAL)

    assert project.inputs["zonal_means"] == "inputs/zonal_means.csv"
    assert not (project.folder / "inputs" / "zonal_means.xlsx").exists()


def test_c_m1_05_a_dam_sheet_with_another_extension_replaces_the_old_copy(tmp_path, project, data):
    data.import_basin_table(SAMPLE_BASINS)
    workbook = tmp_path / "sheet.xlsx"
    pd.read_csv(SAMPLE_SHEETS["cubuk_1"], encoding="utf-8-sig").to_excel(workbook, index=False)
    data.import_dam_sheets([workbook])
    assert project.dams[1].sheet == "inputs/dams/cubuk_1.xlsx"

    data.import_dam_sheets([SAMPLE_SHEETS["cubuk_1"]])

    assert project.dams[1].sheet == "inputs/dams/cubuk_1.csv"
    assert not (project.folder / "inputs" / "dams" / "cubuk_1.xlsx").exists()


def test_c_m1_08_a_failed_replace_leaves_no_temporary_file(tmp_path, project, data, monkeypatch):
    data.import_basin_table(SAMPLE_BASINS)
    before = data.grid.copy()

    def locked(source, destination):
        raise PermissionError("file is open in another program")

    monkeypatch.setattr("src.services.regional_data.os.replace", locked)
    with pytest.raises(PermissionError):
        data.edit_cell(0, "Main Waterway Slope", "0.99")

    pd.testing.assert_frame_equal(data.grid, before)
    assert sorted(p.name for p in (project.folder / "inputs").iterdir()) == ["basins.csv"]


def test_c_x_05_columns_ignored_in_the_basin_table_are_kept_as_warnings_until_it_is_edited(tmp_path, data):
    path = _csv(tmp_path, "basins.csv", "A,B,S1,100,0.1,north", header=HEADER + ",Region")

    data.import_basin_table(path)

    assert data.basin_warnings == ["basins.csv: ignored column(s) Region."]
    data.edit_cell(0, "Basin Name", "C")
    assert data.basin_warnings == []
