"""C-X-05: every input has one canonical label per column, matched by one rule (D67)."""

import pandas as pd
import pytest

from src.services import labels
from src.services.bedload import load_flow, load_fractions
from src.services.labels import fold, is_monthly_flow_table, match_columns
from src.services.regional import load_basin_table, load_dam_sheet, load_zonal_means
from src.utils.paths import resource_path


def _frame(*columns):
    return pd.DataFrame([[1] * len(columns)], columns=list(columns))


# --- the one rule ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "label"),
    [
        ("DRAINAGE AREA (KM2)", "Drainage Area (km2)"),
        ("  Drainage   Area (km²) ", "Drainage Area (km2)"),
        ("Flow Q (m³/s)", "Flow Q (m3/s)"),
        ("Avg. Slope %", "Avg. Slope"),
        ("avg slope", "Avg. Slope"),
        ("YILLAR", "Yıllar"),
        ("Kasim", "Kasım"),
        ("AĞUSTOS", "Ağustos"),
        ("max res elev", "Max Res. Elev"),
    ],
)
def test_c_x_05_a_header_matches_its_label_by_case_spacing_punctuation_and_superscripts(header, label):
    assert fold(header) == fold(label)


def test_c_x_05_the_matched_columns_come_back_under_their_canonical_labels_in_canonical_order():
    df = _frame("DRAINAGE AREA (KM²)", "main waterway slope", "dam name", "sub-basin  name", "BASIN NAME")

    table, warnings = match_columns(df, "t.csv", labels.BASIN_TABLE)

    assert list(table.columns) == list(labels.BASIN_TABLE) and warnings == []


# --- one label per column: old aliases and other languages are refused -------------------------

RETIRED = [
    (labels.BASIN_TABLE, "Dam Name", "Baraj Adı"),
    (labels.BASIN_TABLE, "Dam Name", "Dam"),
    (labels.BASIN_TABLE, "Basin Name", "Havza"),
    (labels.BASIN_TABLE, "Basin Name", "Basin"),
    (labels.BASIN_TABLE, "Sub-basin Name", "Alt Havza Adı"),
    (labels.BASIN_TABLE, "Sub-basin Name", "Sub-basin"),
    (labels.BASIN_TABLE, "Drainage Area (km2)", "Alan"),
    (labels.BASIN_TABLE, "Drainage Area (km2)", "Area"),
    (labels.BASIN_TABLE, "Main Waterway Slope", "Eğim"),
    (labels.BASIN_TABLE, "Main Waterway Slope", "Slope"),
    (labels.ZONAL, "MEAN", "ORTALAMA"),
    (labels.ZONAL, "Sub-basin Name", "Alt Havza"),
    (labels.FRACTIONS_REQUIRED, "Fi", "share"),
    (labels.DAILY_FLOW, "Date", "Tarih"),
    (labels.DAILY_FLOW, "Flow Q (m3/s)", "Flow"),
    (labels.DAILY_FLOW, "Flow Q (m3/s)", "Debi"),
]


@pytest.mark.parametrize(("required", "label", "retired"), RETIRED)
def test_c_x_05_a_retired_alias_is_refused_naming_the_canonical_label_and_the_columns_present(required, label, retired):
    df = _frame(*[retired if name == label else name for name in required])

    with pytest.raises(ValueError, match="required column") as caught:
        match_columns(df, "t.csv", required)

    assert label in str(caught.value) and retired in str(caught.value) and "t.csv" in str(caught.value)


def test_c_x_05_two_headers_that_mean_one_label_are_an_error_naming_both():
    df = _frame("Dam Name", "dam name", "Basin Name", "Sub-basin Name", "Drainage Area (km2)", "Main Waterway Slope")

    with pytest.raises(ValueError, match="'Dam Name' and 'dam name'"):
        match_columns(df, "t.csv", labels.BASIN_TABLE)


# --- columns outside the format: ignored, but never silently -----------------------------------


def test_c_x_05_columns_outside_the_format_are_ignored_with_one_warning_naming_them():
    df = _frame("di", "Fi", "di_D50", "Aciklama ", "bi")

    table, warnings = match_columns(df, "f.csv", labels.FRACTIONS_REQUIRED, labels.FRACTIONS_OPTIONAL)

    assert list(table.columns) == ["di", "Fi", "bi"]
    assert warnings == ["f.csv: ignored column(s) di_D50, Aciklama ."]


def test_c_x_05_an_empty_unnamed_column_from_a_trailing_delimiter_is_not_reported():
    df = pd.DataFrame({"di": [0.1], "Fi": [1.0], "Unnamed: 2": [float("nan")]})

    _, warnings = match_columns(df, "f.csv", labels.FRACTIONS_REQUIRED, labels.FRACTIONS_OPTIONAL)

    assert warnings == []


def test_c_x_05_optional_labels_are_not_required():
    table, warnings = match_columns(_frame("di", "Fi"), "f.csv", labels.FRACTIONS_REQUIRED, labels.FRACTIONS_OPTIONAL)

    assert list(table.columns) == ["di", "Fi"] and warnings == []


# --- the DSİ monthly layout ---------------------------------------------------------------------


def test_c_x_05_a_dsi_table_is_told_from_a_daily_series_by_its_labels():
    assert is_monthly_flow_table(_frame("Yıllar", *labels.DSI_MONTHS, "TOP."))
    assert is_monthly_flow_table(_frame("Yillar", "Ekim"))
    assert not is_monthly_flow_table(_frame("Date", "Flow Q (m3/s)"))
    assert not is_monthly_flow_table(_frame("Date", "Yıllar", "Ekim"))


def test_c_x_05_the_dsi_layout_is_the_year_column_and_twelve_months_with_an_optional_total():
    df = _frame("YILLAR", "ekim", "KASIM", "Aralik", "Ocak", "Subat", "Mart", "Nisan", "Mayis", "Haziran", "Temmuz")
    df["Agustos"], df["EYLUL"], df["top."] = 1, 1, 1

    table, warnings = match_columns(df, "d.csv", labels.DSI_REQUIRED, labels.DSI_OPTIONAL)

    assert list(table.columns) == [*labels.DSI_REQUIRED, "TOP."] and warnings == []


# --- the shipped samples are the reference format ----------------------------------------------


def test_c_x_05_every_shipped_sample_loads_without_a_warning():
    basins = load_basin_table(resource_path("inputs", "master_yield.csv")).data

    assert load_zonal_means(resource_path("inputs", "raw_zonal_means.csv")).warnings == []
    assert load_fractions(resource_path("inputs", "fractional_parameters.csv")).warnings == []
    for sheet in sorted(resource_path("inputs", "bathymetry").glob("*.csv")):
        assert load_dam_sheet(sheet, basins).warnings == [], sheet.name
    for flow in sorted(resource_path("inputs", "dam_flow_data").glob("*.csv")):
        assert load_flow(flow, 0.6, 0).synthetic, flow.name
