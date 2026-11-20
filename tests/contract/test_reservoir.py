"""C-M4-01: the curve sheet of one dam, its import into the project and the curve service (FR-M4-01, FR-M4-02, D75)."""

import json

import pandas as pd
import pytest

from src.services.project import Project
from src.services.regional import DamSheet, TableError
from src.services.reservoir import (
    CSV_NAME,
    compute_curve,
    compute_dam_curve,
    import_curve_sheet,
    load_curve_sheet,
    validate_curve_sheet,
    write_reservoir_csv,
)
from tests.samples import sample_curve, sample_sheet

HEADER = "Elevation (m),Volume (hm3),Surface Area (km2)\n"
ROWS = "100,0,0.5\n110,10,1.5\n120,30,2.5\n130,60,3.5\n"


def _sheet(**changes) -> DamSheet:
    """A dam sheet that agrees with ROWS."""
    values = {
        "name": "Kavşakkaya",
        "bed_elev_m": 100.0,
        "crest_elev_m": 130.0,
        "max_elev_m": 125.0,
        "active_vol_hm3": 35.0,
        "max_vol_hm3": 45.0,
        "drainage_area_km2": 309.2,
    }
    return DamSheet(**{**values, **changes})


def _write(folder, text, name="curve.csv", encoding="utf-8"):
    path = folder / name
    path.write_text(text, encoding=encoding)
    return path


@pytest.fixture()
def project(tmp_path):
    project = Project.new(tmp_path / "project", "Region")
    project.add_dam("Kavşakkaya")
    project.save()
    return project


# --- the curve sheet --------------------------------------------------------------------------


def test_c_m4_01_a_curve_sheet_is_read_under_the_result_columns(tmp_path):
    table, warnings = load_curve_sheet(_write(tmp_path, HEADER + ROWS))

    assert list(table.columns) == ["Elevation_m", "Volume_hm3", "Area_km2"] and warnings == []
    assert list(table["Volume_hm3"]) == [0.0, 10.0, 30.0, 60.0]


def test_c_m4_01_the_sample_curve_sheet_loads_without_a_warning():
    table, warnings = load_curve_sheet(sample_curve("kavsakkaya"))

    assert len(table) == 69 and warnings == []
    assert table["Elevation_m"].iloc[0] == 1055.0 and table["Elevation_m"].iloc[-1] == 1124.0


def test_c_m4_01_the_labels_match_by_the_one_rule_and_extra_columns_are_ignored_with_a_warning(tmp_path):
    text = "elevation (M),VOLUME (hm³),surface area (km²),Note\n100,0,0.5,a\n110,10,1.5,b\n"

    table, warnings = load_curve_sheet(_write(tmp_path, text))

    assert len(table) == 2 and len(warnings) == 1 and "Note" in warnings[0]


def test_c_m4_01_a_missing_column_names_the_labels(tmp_path):
    with pytest.raises(ValueError, match="Surface Area \\(km2\\)"):
        load_curve_sheet(_write(tmp_path, "Elevation (m),Volume (hm3)\n100,0\n"))


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ("100,0,0.5\n110,x,1.5\n", "row 3: 'Volume (hm3)' must be a number, found 'x'"),
        ("100,0,0.5\n110,,1.5\n", "row 3: 'Volume (hm3)' must be a number, found an empty cell"),
        ('100,0,0.5\n110,"10,5",1.5\n', "row 3: 'Volume (hm3)' must be a number"),  # a decimal comma is refused
        ("100,0,0.5\n100,10,1.5\n", "row 3: the level 100 m does not rise"),
        ("100,5,0.5\n110,5,1.5\n", "row 3: the volume 5 hm³ does not rise"),
        ("100,0,0.5\n", "at least two rows"),
    ],
)
def test_c_m4_01_an_invalid_curve_sheet_is_refused_and_named(tmp_path, rows, expected):
    with pytest.raises(TableError, match="curve.csv") as raised:
        load_curve_sheet(_write(tmp_path, HEADER + rows))

    assert expected in str(raised.value)


def test_c_m4_01_blank_rows_are_skipped_and_the_rows_keep_their_numbers(tmp_path):
    with pytest.raises(TableError, match="row 4: the volume 5 hm³"):
        validate_curve_sheet(
            pd.DataFrame(
                {
                    "Elevation (m)": ["100", "", "110"],
                    "Volume (hm3)": ["5", "", "5"],
                    "Surface Area (km2)": ["1", "", "2"],
                }
            ),
            "curve.csv",
        )


def test_c_m4_01_a_turkish_encoded_curve_sheet_is_read(tmp_path):
    path = tmp_path / "curve.csv"
    path.write_bytes((HEADER + ROWS).encode("cp1254"))

    assert len(load_curve_sheet(path).data) == 4


# --- the import -------------------------------------------------------------------------------


def test_c_m4_01_import_copies_the_sheet_into_the_project_and_keeps_it_on_the_dam(project, tmp_path):
    source = _write(tmp_path, HEADER + ROWS, "Kavşakkaya eğrisi.csv")
    dam = project.dams[0]

    import_curve_sheet(project, dam, source)

    assert dam.curve_sheet == "inputs/curves/kavsakkaya_curve.csv"
    assert (project.folder / dam.curve_sheet).read_text(encoding="utf-8") == HEADER + ROWS
    assert source.read_text(encoding="utf-8") == HEADER + ROWS
    assert Project.open(project.folder).dams[0].curve_sheet == dam.curve_sheet


def test_c_m4_01_an_invalid_sheet_is_not_imported(project, tmp_path):
    dam = project.dams[0]

    with pytest.raises(ValueError):
        import_curve_sheet(project, dam, _write(tmp_path, HEADER + "100,0,0.5\n100,1,1\n"))

    assert dam.curve_sheet is None and not (project.folder / "inputs" / "curves").exists()


def test_c_m4_01_a_new_sheet_replaces_the_old_copy(project, tmp_path):
    dam = project.dams[0]
    workbook = tmp_path / "a.xlsx"
    pd.read_csv(_write(tmp_path, HEADER + ROWS)).to_excel(workbook, index=False)
    import_curve_sheet(project, dam, workbook)
    old = project.folder / dam.curve_sheet
    assert old.name == "kavsakkaya_curve.xlsx"

    import_curve_sheet(project, dam, _write(tmp_path, HEADER + ROWS, "b.csv"))

    assert dam.curve_sheet == "inputs/curves/kavsakkaya_curve.csv" and not old.exists()


def test_c_m4_01_a_failed_save_restores_the_dam(project, tmp_path, monkeypatch):
    dam = project.dams[0]

    def fail():
        raise OSError("disk full")

    monkeypatch.setattr(project, "save", fail)
    with pytest.raises(OSError):
        import_curve_sheet(project, dam, _write(tmp_path, HEADER + ROWS))

    assert dam.curve_sheet is None


def test_c_m4_01_a_project_of_schema_version_1_opens_without_the_generated_curve(project):
    path = project.folder / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = 1
    data["dams"][0] |= {"curve": {"max_elev_m": 1121.0}, "h_min_m": 1090.0, "shape_class": "hill"}
    del data["dams"][0]["curve_sheet"]
    path.write_text(json.dumps(data), encoding="utf-8")

    dam = Project.open(project.folder).dams[0]

    assert dam.curve_sheet is None and not hasattr(dam, "shape_class")


# --- the curve --------------------------------------------------------------------------------


def test_c_m4_01_the_curve_reads_the_dam_sheet_and_hmin_from_the_curve(tmp_path):
    table, _ = load_curve_sheet(_write(tmp_path, HEADER + ROWS))

    result = compute_curve(table, _sheet())

    assert result.curve.h_min_m == 110.0 and result.curve.max_vol_hm3 == 45.0 and result.warnings == []
    assert result.table.equals(table)


def test_c_m4_01_a_dam_sheet_the_curve_does_not_cover_is_refused_with_every_problem(tmp_path):
    table, _ = load_curve_sheet(_write(tmp_path, HEADER + ROWS))

    with pytest.raises(ValueError, match="cannot be used") as raised:
        compute_curve(table, _sheet(crest_elev_m=140.0, max_vol_hm3=100.0, active_vol_hm3=30.0))

    assert "Hcrest on the dam sheet (140 m)" in str(raised.value) and "Vdead = Vmax - Vactive (70 hm³)" in str(
        raised.value
    )


def test_c_m4_01_the_warnings_of_reading_and_of_the_curve_reach_the_result(tmp_path):
    table, _ = load_curve_sheet(_write(tmp_path, HEADER + ROWS))

    result = compute_curve(table, _sheet(drainage_area_km2=2.0), ["curve.csv: ignored column(s) Note."])

    assert len(result.warnings) == 2 and "Note" in result.warnings[0] and "drainage area" in result.warnings[1]


def test_c_m4_01_a_dam_curve_is_made_from_its_imported_sheet(project, tmp_path):
    dam = project.dams[0]
    import_curve_sheet(project, dam, _write(tmp_path, HEADER + ROWS))

    result = compute_dam_curve(project, _sheet(), dam)

    assert result.curve.h_min_m == 110.0


def test_x_01_a_dam_without_a_curve_sheet_says_where_to_import_it(project):
    with pytest.raises(ValueError, match="no reservoir curve sheet. Import it in step 6"):
        compute_dam_curve(project, _sheet(), project.dams[0])


def test_c_m4_01_the_kavsakkaya_dam_sheet_fits_its_curve_sheet(project):
    """OI-11: the operating values the hydrologist gave (Vdead = 80.83 - 76.14 hm³) with the measured curve."""
    from src.services.regional import validate_dam_sheet
    from src.utils.paths import read_table

    basins = pd.DataFrame(
        {"Dam Name": ["Kavşakkaya"], "Basin Name": ["B"], "Sub-basin Name": ["S"], "Drainage Area (km2)": [309.2]}
        | {"Main Waterway Slope": [0.23]}
    )
    sheet = validate_dam_sheet(read_table(sample_sheet("kavsakkaya")), "sheet", basins).data
    table, _ = load_curve_sheet(sample_curve("kavsakkaya"))

    curve = compute_curve(table, sheet).curve

    assert curve.bed_elev_m == 1059.0 and curve.dead_vol_hm3 == pytest.approx(4.69)
    assert curve.h_min_m == pytest.approx(1071.9946, abs=1e-4)


def test_c_m4_01_the_curve_is_written_as_utf8_with_bom_and_unit_named_columns(tmp_path):
    table, _ = load_curve_sheet(_write(tmp_path, HEADER + ROWS))

    path = write_reservoir_csv(compute_curve(table, _sheet()), tmp_path)

    assert path == tmp_path / CSV_NAME
    assert path.read_bytes().startswith(b"\xef\xbb\xbfElevation_m,Volume_hm3,Area_km2")
