import pandas as pd
import pytest

from src.services.regional import (
    DamSheet,
    TableError,
    load_basin_table,
    load_dam_sheet,
    load_zonal_means,
    name_key,
    parse_number,
    validate_basin_table,
    validate_dam_sheet,
    validate_zonal_means,
)
from src.utils.paths import resource_path

CANONICAL = ["Dam Name", "Basin Name", "Sub-basin Name", "Drainage Area (km2)", "Main Waterway Slope"]
BASIN_HEADER = ",".join(CANONICAL)
SAMPLE_BASINS = resource_path("inputs", "master_yield.csv")
SAMPLE_ZONAL = resource_path("inputs", "raw_zonal_means.csv")
SHEET_HEADER = (
    "Dam Name,Drainage Area (km2),Longest River Length (km),Top Elevation of River,Bottom Elevation of River,"
    "Average Slope,Crest Elevation,Maximum Reservoir Elevation,Active Volume,Maximum Volume,Average Flow"
)
CUBUK_1_ROW = "Çubuk 1,834.7,25.5,1109,888,0.09,908.6,907.6,5.28,5.6,62.6"


def _write(tmp_path, name, text, encoding="utf-8-sig"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


def _basins(tmp_path, *rows, header=BASIN_HEADER):
    return _write(tmp_path, "basins.csv", "\n".join([header, *rows]) + "\n")


def _sheet(tmp_path, row=CUBUK_1_ROW, header=SHEET_HEADER):
    return _write(tmp_path, "sheet.csv", f"{header}\n{row}\n")


@pytest.fixture()
def sample_table():
    return load_basin_table(SAMPLE_BASINS).data


# --- basin table (FR-M1-03) -------------------------------------------------------------------


def test_c_m1_03_sample_basin_table_loads_to_canonical_columns():
    loaded = load_basin_table(SAMPLE_BASINS)

    assert list(loaded.data.columns) == CANONICAL
    assert loaded.data["Dam Name"].tolist() == ["Kavşakkaya", "Çubuk 1", "Çubuk 2"]
    assert loaded.data["Drainage Area (km2)"].tolist() == [309.2, 834.7, 180.2]
    assert loaded.data["Main Waterway Slope"].tolist() == [0.23, 0.09, 0.16]
    assert loaded.warnings == []


def test_c_m1_03_turkish_headers_are_refused_naming_the_canonical_labels(tmp_path):
    path = _write(
        tmp_path,
        "tr.csv",
        "Baraj Adı,Havza,Alt Havza Adı,Alan (km2),Eğim\nÇubuk 1,Sakarya,Ankara Alt Havzası,834.7,0.09\n",
    )

    with pytest.raises(ValueError, match="required column") as error:
        load_basin_table(path)

    assert all(label in str(error.value) for label in CANONICAL) and "Baraj Adı" in str(error.value)


def test_c_m1_04_blank_rows_are_skipped(tmp_path):
    path = _basins(tmp_path, "A,B,S1,10,0.1", ",,,,", "A,B,S2,20,0.2", " , , , , ")

    data = load_basin_table(path).data

    assert data["Sub-basin Name"].tolist() == ["S1", "S2"]


def test_c_m1_04_same_sub_basin_name_in_different_dams_is_allowed(tmp_path):
    path = _basins(tmp_path, "A,B,Ankara Alt Havzası,10,0.1", "C,B,Ankara Alt Havzası,20,0.2")

    assert len(load_basin_table(path).data) == 2


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        (["A,B,S1,10,0.1", ",B,S2,20,0.2"], ["row 3", "Dam Name", "empty"]),
        (["A,B,S1,0,0.1"], ["row 2", "Drainage Area (km2)", "greater than 0"]),
        (["A,B,S1,-5,0.1"], ["row 2", "Drainage Area (km2)", "-5"]),
        (["A,B,S1,abc,0.1"], ["row 2", "Drainage Area (km2)", "'abc'"]),
        (["A,B,S1,10,"], ["row 2", "Main Waterway Slope", "number"]),
        (["A,B,S1,10,steep"], ["row 2", "Main Waterway Slope", "'steep'"]),
        (["A,B,S1,10,0.1", "A,B,s1 ,20,0.2"], ["rows 2 and 3", "appears twice", "'A'"]),
        (["A,B,Ankara Alt Havzası,10,0.1", "A,B,ANKARA ALT HAVZASI,20,0.2"], ["rows 2 and 3", "appears twice"]),
    ],
)
def test_c_m1_04_invalid_rows_are_reported_with_their_location(tmp_path, rows, expected):
    path = _basins(tmp_path, *rows)

    with pytest.raises(ValueError) as error:
        load_basin_table(path)

    message = str(error.value)
    assert "basins.csv" in message
    for fragment in expected:
        assert fragment in message


def test_c_m1_04_every_problem_is_listed(tmp_path):
    path = _basins(tmp_path, "A,B,S1,0,0.1", "A,B,S2,10,x")

    with pytest.raises(ValueError) as error:
        load_basin_table(path)

    assert "row 2" in str(error.value)
    assert "row 3" in str(error.value)


def test_c_m1_04_missing_columns_are_named(tmp_path):
    path = _basins(tmp_path, "A,B,S1,10", header="Dam Name,Basin Name,Sub-basin Name,Drainage Area (km2)")

    with pytest.raises(ValueError, match=r"required column.*Main Waterway Slope"):
        load_basin_table(path)


def test_c_m1_04_a_table_without_data_rows_is_an_error(tmp_path):
    path = _basins(tmp_path, ",,,,")

    with pytest.raises(ValueError, match="no data rows"):
        load_basin_table(path)


def test_c_m1_04_validate_basin_table_accepts_an_edited_grid():
    grid = pd.DataFrame(
        {
            "Dam Name": ["A"],
            "Basin Name": ["B"],
            "Sub-basin Name": ["S1"],
            "Drainage Area (km2)": ["12.5"],
            "Main Waterway Slope": [0.1],
        }
    )

    loaded = validate_basin_table(grid, "grid")

    assert loaded.data["Drainage Area (km2)"].tolist() == [12.5]


# --- dam sheet (FR-M1-05, FR-M1-06) -----------------------------------------------------------

EXPECTED_SHEETS = {
    "kavsakkaya": DamSheet("Kavşakkaya", 1063.0, 1124.0, 1122.3, 74.1, 80.8, 309.2, 0.23, 41.6, 2009.0, 66.5),
    "cubuk_1": DamSheet("Çubuk 1", 888.0, 908.6, 907.6, 5.28, 5.6, 834.7, 0.09, 25.5, 1109.0, 62.6),
    "cubuk_2": DamSheet("Çubuk 2", 1110.0, 1117.0, 1115.3, 22.0, 22.4, 180.2, 0.16, 42.2, 1766.0, 30.1),
}


@pytest.mark.parametrize("slug", sorted(EXPECTED_SHEETS))
def test_c_m1_05_sample_dam_sheets_load_without_warnings(sample_table, slug):
    path = resource_path("inputs", "bathymetry", f"{slug}_bathymetry.csv")

    loaded = load_dam_sheet(path, sample_table)

    assert loaded.data == EXPECTED_SHEETS[slug]
    assert loaded.warnings == []


@pytest.mark.parametrize("name", ["CUBUK 1", "ÇUBUK 1", "çubuk   1"])
def test_c_m1_05_dam_name_matches_the_basin_table_turkish_aware(tmp_path, sample_table, name):
    row = CUBUK_1_ROW.replace("Çubuk 1", name, 1)

    loaded = load_dam_sheet(_sheet(tmp_path, row), sample_table)

    assert loaded.warnings == []


def test_c_m1_05_unknown_dam_is_an_error_naming_it(tmp_path, sample_table):
    row = CUBUK_1_ROW.replace("Çubuk 1", "Sariyar", 1)

    with pytest.raises(ValueError) as error:
        load_dam_sheet(_sheet(tmp_path, row), sample_table)

    assert "sheet.csv" in str(error.value)
    assert "Sariyar" in str(error.value)
    assert "Çubuk 1" in str(error.value)


def test_c_m1_05_missing_required_columns_are_named(tmp_path, sample_table):
    header = SHEET_HEADER.replace("Bottom Elevation of River,", "").replace("Maximum Volume,", "")
    row = "Çubuk 1,834.7,25.5,1109,0.09,908.6,907.6,5.28,62.6"

    with pytest.raises(ValueError) as error:
        load_dam_sheet(_sheet(tmp_path, row, header), sample_table)

    assert "Bottom Elevation of River" in str(error.value)
    assert "Maximum Volume" in str(error.value)


def test_c_m1_05_blank_or_non_numeric_required_values_are_named(tmp_path, sample_table):
    row = "Çubuk 1,834.7,25.5,1109,,0.09,908.6,high,5.28,5.6,62.6"

    with pytest.raises(ValueError) as error:
        load_dam_sheet(_sheet(tmp_path, row), sample_table)

    message = str(error.value)
    assert "Bottom Elevation of River" in message
    assert "Maximum Reservoir Elevation" in message
    assert "'high'" in message


def test_c_m1_05_a_sheet_holds_exactly_one_dam(tmp_path, sample_table):
    path = _write(
        tmp_path,
        "sheet.csv",
        SHEET_HEADER + "\n" + CUBUK_1_ROW + "\nÇubuk 2,180.2,42.2,1766,1110,0.16,1117,1115.3,22,22.4,30.1\n",
    )

    with pytest.raises(ValueError, match="exactly one"):
        load_dam_sheet(path, sample_table)


def test_c_m1_05_optional_columns_may_be_absent(tmp_path, sample_table):
    header = (
        "Dam Name,Bottom Elevation of River,Crest Elevation,Maximum Reservoir Elevation,Active Volume,Maximum Volume"
    )
    path = _sheet(tmp_path, "Çubuk 1,888,908.6,907.6,5.28,5.6", header)

    sheet = load_dam_sheet(path, sample_table).data

    assert sheet.drainage_area_km2 is None
    assert sheet.slope_m_per_m is None
    assert sheet.max_vol_hm3 == 5.6


@pytest.mark.parametrize(
    ("area", "slope", "expect_area", "expect_slope"),
    [
        ("834.7", "0.09", False, False),
        ("839.0", "0.09", False, False),  # 0.5% off: inside the tolerance
        ("900", "0.09", True, False),
        ("834.7", "0.12", False, True),
        ("700", "0.20", True, True),
    ],
)
def test_c_m1_06_area_and_slope_are_cross_checked_against_the_table(
    tmp_path, sample_table, area, slope, expect_area, expect_slope
):
    row = f"Çubuk 1,{area},25.5,1109,888,{slope},908.6,907.6,5.28,5.6,62.6"

    warnings = load_dam_sheet(_sheet(tmp_path, row), sample_table).warnings

    assert any("drainage area" in w for w in warnings) is expect_area
    assert any("slope" in w for w in warnings) is expect_slope
    assert all("sheet.csv" in w for w in warnings)


def test_c_m1_06_cross_check_uses_the_sum_of_the_dams_sub_basins(tmp_path):
    table = load_basin_table(_basins(tmp_path, "A,B,S1,100,0.1", "A,B,S2,300,0.3", "Z,B,S1,50,0.5")).data
    row = "A,400,1,1,1,0.25,2,2,1,2,1"  # area-weighted mean slope: (100*0.1 + 300*0.3) / 400 = 0.25

    loaded = load_dam_sheet(_sheet(tmp_path, row), table)

    assert loaded.warnings == []


# --- zonal means (FR-M1-06) -------------------------------------------------------------------


def test_c_m1_07_sample_zonal_means_load():
    loaded = load_zonal_means(SAMPLE_ZONAL)

    assert list(loaded.data.columns) == ["Sub-basin Name", "MEAN"]
    assert len(loaded.data) == 6
    assert loaded.data.loc[1, "Sub-basin Name"] == "Ankara Alt Havzası"
    assert loaded.data.loc[1, "MEAN"] == pytest.approx(3.148701574)
    assert loaded.warnings == []


def test_c_m1_07_labels_are_found_whatever_their_case_and_spacing(tmp_path):
    path = _write(tmp_path, "z.csv", "sub-basin  NAME,Mean\nAnkara Alt Havzası,3.1\n")

    assert load_zonal_means(path).data["MEAN"].tolist() == [3.1]


def test_c_m1_07_rows_with_empty_or_non_numeric_means_are_skipped_and_counted(tmp_path):
    path = _write(tmp_path, "z.csv", "Sub-basin Name,MEAN\nA,1.5\nB,\nC,n/a\n,2.0\nD,2.5\n")

    loaded = load_zonal_means(path)

    assert loaded.data["Sub-basin Name"].tolist() == ["A", "D"]
    assert len(loaded.warnings) == 1
    assert "z.csv" in loaded.warnings[0]
    assert "skipped 3 row(s)" in loaded.warnings[0]
    assert "rows 3, 4, 5" in loaded.warnings[0]


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("Sub-basin Name,Value\nA,1\n", "MEAN"),
        ("Zone,MEAN\nA,1\n", "Sub-basin Name"),
        ("Sub-basin Name,MEAN\nA,\nB,x\n", "no valid"),
    ],
)
def test_c_m1_07_unusable_zonal_files_are_errors(tmp_path, text, fragment):
    with pytest.raises(ValueError) as error:
        load_zonal_means(_write(tmp_path, "z.csv", text))

    assert "z.csv" in str(error.value)
    assert fragment in str(error.value)


# --- cross-cutting (FR-X-01..03) --------------------------------------------------------------


def test_c_x_01_a_missing_input_is_an_error_naming_it(tmp_path, sample_table):
    missing = tmp_path / "not_there.csv"

    for call in (
        lambda: load_basin_table(missing),
        lambda: load_zonal_means(missing),
        lambda: load_dam_sheet(missing, sample_table),
    ):
        with pytest.raises(FileNotFoundError, match="not_there.csv"):
            call()


def test_c_x_01_unreadable_files_are_errors_naming_them(tmp_path):
    empty = _write(tmp_path, "empty.csv", "")
    unsupported = _write(tmp_path, "table.txt", "a,b\n1,2\n")

    for path in (empty, unsupported):
        with pytest.raises(ValueError, match=path.name):
            load_basin_table(path)


TURKISH_ROWS = [
    ("Çubuk 1", "Sakarya", "Ankara Alt Havzası", 834.7, 0.09),
    ("Kavşakkaya", "Sakarya", "Ankara Alt Havzası", 309.2, 0.23),
    ("İznik Barajı", "Marmara", "Göksu Alt Havzası", 12.5, 0.16),
]


def _turkish_csv(separator, decimal):
    lines = [separator.join(CANONICAL)]
    for dam, basin, sub, area, slope in TURKISH_ROWS:
        numbers = [str(area).replace(".", decimal), str(slope).replace(".", decimal)]
        lines.append(separator.join([dam, basin, sub, *numbers]))
    return "\r\n".join(lines) + "\r\n"


@pytest.mark.parametrize(
    ("encoding", "separator"),
    [("utf-8-sig", ","), ("utf-8", ","), ("cp1254", ","), ("cp1254", ";"), ("iso-8859-9", ";")],
)
def test_c_x_02_encodings_and_separators_load_identically(tmp_path, encoding, separator):
    reference = load_basin_table(_write(tmp_path, "reference.csv", _turkish_csv(",", "."))).data
    path = _write(tmp_path, "variant.csv", _turkish_csv(separator, "."), encoding)

    loaded = load_basin_table(path).data

    pd.testing.assert_frame_equal(loaded, reference)
    assert loaded["Dam Name"].tolist() == [row[0] for row in TURKISH_ROWS]


@pytest.mark.parametrize("text", ["1,5", "834,7", "1,234", "1.234,5"])
def test_c_x_02_a_comma_is_never_read_as_a_decimal_point(text):
    assert parse_number(text) is None


def test_c_x_02_a_decimal_comma_in_a_semicolon_file_is_refused(tmp_path):
    path = _write(tmp_path, "comma.csv", _turkish_csv(";", ","), "cp1254")

    with pytest.raises(TableError):
        load_basin_table(path)


def test_c_x_02_rows_with_more_fields_than_the_header_are_refused_not_shifted(tmp_path):
    # "309,2" in a comma-separated file is two fields, so every row is one longer than the header.
    path = _basins(
        tmp_path, "Kavşakkaya,Sakarya,Ankara Alt Havzası,309,2,0.23", "Çubuk 1,Sakarya,Ankara Alt Havzası,834,7,0.09"
    )

    with pytest.raises(ValueError, match="more values than the header"):
        load_basin_table(path)


def test_c_x_02_a_separator_at_the_end_of_every_row_is_refused_and_named(tmp_path):
    path = _basins(tmp_path, "Kavşakkaya,Sakarya,Ankara Alt Havzası,309.2,0.23,", "Çubuk 1,Sakarya,Ankara,834.7,0.09,")

    with pytest.raises(ValueError, match="separator at the end of every row"):
        load_basin_table(path)


def test_c_x_04_a_validation_error_names_the_file_the_row_and_the_column(tmp_path):
    path = _basins(
        tmp_path, "Kavşakkaya,Sakarya,Ankara Alt Havzası,309.2,0.23", "Çubuk 1,Sakarya,Ankara Alt Havzası,x,0.09"
    )

    with pytest.raises(TableError) as raised:
        load_basin_table(path)

    message = str(raised.value)
    assert "basins.csv" in message and "row 3" in message and "'Drainage Area (km2)'" in message
    assert raised.value.problems[0].cells == ((3, "Drainage Area (km2)"),)


def test_c_x_03_name_key_folds_turkish_case_and_spacing():
    assert name_key("  ÇUBUK   1 ") == name_key("Çubuk 1") == name_key("cubuk 1")
    assert name_key("İznik Barajı") == name_key("IZNIK BARAJI") == name_key("iznik baraji")


# --- review follow-ups ------------------------------------------------------------------------


def test_c_x_02_an_excel_table_loads_like_the_csv(tmp_path):
    reference = load_basin_table(SAMPLE_BASINS).data
    path = tmp_path / "basins.xlsx"
    pd.read_csv(SAMPLE_BASINS, encoding="utf-8-sig").to_excel(path, index=False)

    loaded = load_basin_table(path).data

    pd.testing.assert_frame_equal(loaded, reference)


def test_c_x_02_an_old_excel_xls_table_is_read(tmp_path):
    # tests/data/basins.xls is one Çubuk 1 row in the old binary format, which pandas reads through xlrd.
    loaded = load_basin_table(resource_path("tests", "data", "basins.xls")).data

    assert loaded.iloc[0].tolist() == ["Çubuk 1", "Sakarya", "Ankara Alt Havzası", 834.7, 0.09]


@pytest.mark.parametrize("name", ["corrupt.xlsx", "corrupt.xls"])
def test_c_x_01_a_corrupt_excel_file_is_an_error_naming_it(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"this is not a spreadsheet")

    with pytest.raises(ValueError, match=name):
        load_basin_table(path)


def test_c_m1_07_validate_zonal_means_accepts_an_in_memory_table():
    grid = pd.DataFrame({"Sub-basin Name": ["A", "B"], "MEAN": [1.5, None]})

    loaded = validate_zonal_means(grid, "grid")

    assert loaded.data["Sub-basin Name"].tolist() == ["A"]
    assert "skipped 1 row(s)" in loaded.warnings[0]


def test_c_m1_05_validate_dam_sheet_accepts_an_in_memory_table(sample_table):
    grid = pd.read_csv(resource_path("inputs", "bathymetry", "cubuk_1_bathymetry.csv"), encoding="utf-8-sig")

    loaded = validate_dam_sheet(grid, "grid", sample_table)

    assert loaded.data == EXPECTED_SHEETS["cubuk_1"]


def test_c_m1_06_a_sheet_covering_only_part_of_the_dams_area_is_flagged(tmp_path):
    table = load_basin_table(_basins(tmp_path, "A,B,S1,100,0.2", "A,B,S2,300,0.2")).data
    row = "A,100,1,1,1,0.2,2,2,1,2,1"  # the table holds 400 km2 for dam A

    warnings = load_dam_sheet(_sheet(tmp_path, row), table).warnings

    assert len(warnings) == 1
    assert "drainage area" in warnings[0]
    assert "400" in warnings[0]


def test_c_m1_05_the_first_spelling_of_a_dam_in_the_table_names_it(tmp_path):
    table = load_basin_table(_basins(tmp_path, "Çubuk 1,B,S1,100,0.2", "CUBUK 1,B,S2,300,0.2")).data
    row = "cubuk 1,400,1,1,1,0.2,2,2,1,2,1"

    assert load_dam_sheet(_sheet(tmp_path, row), table).data.name == "Çubuk 1"


def test_c_x_01_a_truncated_workbook_is_an_error_naming_it(tmp_path):
    path = tmp_path / "truncated.xlsx"
    pd.read_csv(SAMPLE_BASINS, encoding="utf-8-sig").to_excel(path, index=False)
    path.write_bytes(path.read_bytes()[:300])

    with pytest.raises(ValueError, match="truncated.xlsx"):
        load_basin_table(path)
