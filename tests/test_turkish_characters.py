import os
import tempfile
import tkinter as tk
from pathlib import Path

import pandas as pd
import pytest

from app import SedimentApp
from src.core.rusle import (
    ZonalMatcher,
    find_basin_table_columns,
    normalize_header,
    to_ascii_turkish,
    turkish_lower,
)
from src.data.database import BasinDatabase
from src.utils.paths import read_table


@pytest.fixture
def sample_turkish_data():
    return pd.DataFrame(
        {
            "Dam Name": [
                "Atatürk Barajı",
                "Keban Barajı",
                "Deriner Barajı",
                "Gökçekaya Barajı",
                "Ömerli Barajı",
                "İkizdere Barajı",
            ],
            "Basin Name": [
                "Fırat Havzası",
                "Fırat Havzası",
                "Çoruh Havzası",
                "Sakarya Havzası",
                "Marmara Havzası",
                "Doğu Karadeniz Havzası",
            ],
            "Sub-basin Name": [
                "Aşağı Fırat Alt Havzası",
                "Yukarı Fırat Alt Havzası",
                "Çoruh Alt Havzası",
                "Porsuk Alt Havzası",
                "Ömerli Alt Havzası",
                "İyidere Alt Havzası",
            ],
            "Area": [1250.5, 980.2, 450.0, 720.4, 310.8, 195.6],
            "Main Waterway Slope": [0.012, 0.018, 0.035, 0.015, 0.009, 0.042],
        }
    )


@pytest.mark.parametrize(
    "header, expected",
    [
        ("Flow Q (m³/s)", "flowq(m3/s)"),
        ("Yıllar", "yillar"),
        ("YILLAR", "yillar"),
        ("TOP.", "top"),
        ("ORT.", "ort"),
        ("Ağustos", "agustos"),
        ("Eylül", "eylul"),
        (" Tarih ", "tarih"),
        ("Water_Year", "water_year"),
    ],
)
def test_normalize_header(header, expected):
    assert normalize_header(header) == expected


def test_turkish_string_helpers():
    # Turkish lower casing rules
    assert turkish_lower("IŞIK") == "ışık"
    assert turkish_lower("İSTANBUL") == "istanbul"
    assert turkish_lower("ÇORUH") == "çoruh"
    assert turkish_lower("GÖKSU") == "göksu"
    assert turkish_lower("AŞAĞI") == "aşağı"
    assert turkish_lower("DÜZCE") == "düzce"

    # Transliteration to ASCII
    assert to_ascii_turkish("ışık") == "isik"
    assert to_ascii_turkish("istanbul") == "istanbul"
    assert to_ascii_turkish("çoruh") == "coruh"
    assert to_ascii_turkish("göksu") == "goksu"
    assert to_ascii_turkish("aşağı") == "asagi"
    assert to_ascii_turkish("düzce") == "duzce"
    assert to_ascii_turkish("ÖMERLİ") == "OMERLI"


def test_read_table_turkish_encodings(tmp_path, sample_turkish_data):
    encodings = ["utf-8-sig", "utf-8", "cp1254", "iso-8859-9"]
    for enc in encodings:
        file_path = tmp_path / f"basins_{enc}.csv"
        sample_turkish_data.to_csv(file_path, index=False, encoding=enc)
        df_read = read_table(str(file_path))

        assert len(df_read) == len(sample_turkish_data)
        assert df_read["Dam Name"].tolist() == sample_turkish_data["Dam Name"].tolist()
        assert df_read["Basin Name"].tolist() == sample_turkish_data["Basin Name"].tolist()
        assert df_read["Sub-basin Name"].tolist() == sample_turkish_data["Sub-basin Name"].tolist()


def test_read_table_semicolon_delimited_csv(tmp_path, sample_turkish_data):
    file_path = tmp_path / "basins_semicolon.csv"
    sample_turkish_data.to_csv(file_path, index=False, sep=";", encoding="utf-8-sig")
    df_read = read_table(str(file_path))

    assert len(df_read.columns) == 5
    assert "Dam Name" in df_read.columns
    assert df_read.iloc[0]["Dam Name"] == "Atatürk Barajı"


def test_read_table_excel_turkish(tmp_path, sample_turkish_data):
    file_path = tmp_path / "basins.xlsx"
    sample_turkish_data.to_excel(file_path, index=False)
    df_read = read_table(str(file_path))

    assert len(df_read) == len(sample_turkish_data)
    assert df_read["Dam Name"].tolist() == sample_turkish_data["Dam Name"].tolist()


def test_find_basin_table_columns_turkish_and_english():
    en_cols = ["Dam Name", "Basin Name", "Sub-basin Name", "Area", "Main Waterway Slope"]
    col_map_en = find_basin_table_columns(en_cols)
    assert col_map_en["dam"] == "Dam Name"
    assert col_map_en["basin"] == "Basin Name"
    assert col_map_en["subbasin"] == "Sub-basin Name"
    assert col_map_en["area"] == "Area"
    assert col_map_en["slope"] == "Main Waterway Slope"

    tr_cols = ["Baraj Adı", "Havza Adı", "Alt Havza Adı", "Alan (km2)", "Eğim"]
    col_map_tr = find_basin_table_columns(tr_cols)
    assert col_map_tr["dam"] == "Baraj Adı"
    assert col_map_tr["basin"] == "Havza Adı"
    assert col_map_tr["subbasin"] == "Alt Havza Adı"
    assert col_map_tr["area"] == "Alan (km2)"
    assert col_map_tr["slope"] == "Eğim"


def test_basin_database_turkish(sample_turkish_data):
    db = BasinDatabase()
    db.load_from_dataframe(sample_turkish_data)

    # Exact match
    area, slope = db.get_area_and_slope("Çoruh Havzası", "Çoruh Alt Havzası")
    assert area == 450.0
    assert slope == 0.035

    # Case-insensitive with Turkish characters
    area, slope = db.get_area_and_slope("ÇORUH HAVZASI", "ÇORUH ALT HAVZASI")
    assert area == 450.0

    # ASCII transliterated fallback
    area, slope = db.get_area_and_slope("Coruh Havzasi", "Coruh Alt Havzasi")
    assert area == 450.0


def test_zonal_matcher_turkish_normalization_and_matching():
    # Normalizing with Turkish characters and stripping affixes
    norm = ZonalMatcher.normalize_subbasin_name("Aşağı Sakarya Alt Havzası")
    assert norm == "aşağısakarya"

    aliases = ZonalMatcher.get_subbasin_aliases("Aşağı Sakarya Alt Havzası")
    assert "aşağısakarya" in aliases
    assert "asagisakarya" in aliases
    assert "aşağısakaryaalthavzası" in aliases
    assert "asagisakaryaalthavzasi" in aliases

    # Build lookup with ASCII names (as in actual GIS raw tables)
    zonal_df = pd.DataFrame(
        {
            "Sub-basin": [
                "Asagi sakarya Alt Havzasi",
                "Goksu Alt Havzasi",
                "Coruh Alt Havzasi",
                "Porsuk Alt Havzasi",
            ],
            "MEAN": [3.23, 2.81, 4.15, 2.18],
        }
    )
    lookup = ZonalMatcher.build_lookup(zonal_df)

    # Subbasin queries with Turkish characters match ASCII zonal table entries
    assert ZonalMatcher.resolve_zonal_mean(lookup, "Aşağı Sakarya Alt Havzası") == 3.23
    assert ZonalMatcher.resolve_zonal_mean(lookup, "Aşağı Sakarya") == 3.23
    assert ZonalMatcher.resolve_zonal_mean(lookup, "AŞAĞI SAKARYA ALT HAVZASI") == 3.23
    assert ZonalMatcher.resolve_zonal_mean(lookup, "Göksu Alt Havzası") == 2.81
    assert ZonalMatcher.resolve_zonal_mean(lookup, "GÖKSU") == 2.81
    assert ZonalMatcher.resolve_zonal_mean(lookup, "Çoruh Alt Havzası") == 4.15
    assert ZonalMatcher.resolve_zonal_mean(lookup, "ÇORUH") == 4.15

    # Build lookup with Turkish characters
    zonal_tr_df = pd.DataFrame(
        {
            "Alt Havza": [
                "Aşağı Sakarya Alt Havzası",
                "Göksu Alt Havzası",
                "Ömerli Alt Havzası",
                "İyidere Alt Havzası",
            ],
            "Ortalama": [3.23, 2.81, 1.95, 5.12],
        }
    )
    lookup_tr = ZonalMatcher.build_lookup(zonal_tr_df)
    assert ZonalMatcher.resolve_zonal_mean(lookup_tr, "Aşağı Sakarya Alt Havzası") == 3.23
    assert ZonalMatcher.resolve_zonal_mean(lookup_tr, "Ömerli Alt Havzası") == 1.95
    assert ZonalMatcher.resolve_zonal_mean(lookup_tr, "Ömerli") == 1.95
    assert ZonalMatcher.resolve_zonal_mean(lookup_tr, "İyidere Alt Havzası") == 5.12
    assert ZonalMatcher.resolve_zonal_mean(lookup_tr, "İYİDERE") == 5.12


def test_ui_display_and_workflow_with_turkish_characters(tmp_path, sample_turkish_data, tk_root):
    basin_csv = tmp_path / "turkish_basins.csv"
    sample_turkish_data.to_csv(basin_csv, index=False, encoding="utf-8-sig")

    zonal_csv = tmp_path / "turkish_zonal.csv"
    pd.DataFrame(
        {
            "Sub-basin": [
                "Aşağı Fırat Alt Havzası",
                "Yukarı Fırat Alt Havzası",
                "Çoruh Alt Havzası",
                "Porsuk Alt Havzası",
                "Ömerli Alt Havzası",
                "İyidere Alt Havzası",
            ],
            "MEAN": [3.10, 2.75, 4.20, 2.15, 1.80, 5.05],
        }
    ).to_csv(zonal_csv, index=False, encoding="utf-8-sig")

    root = tk.Toplevel(tk_root)
    try:
        app = SedimentApp(root)

        # 1. Load basin file into UI
        app.rusle_view._populate_basin_tree(str(basin_csv))

        # Verify basin tree displays all rows and Turkish characters
        children = app.basin_tree.get_children()
        assert len(children) == len(sample_turkish_data)

        first_row_vals = app.basin_tree.item(children[0], "values")
        assert first_row_vals[0] == "Atatürk Barajı"
        assert first_row_vals[1] == "Fırat Havzası"
        assert first_row_vals[2] == "Aşağı Fırat Alt Havzası"

        third_row_vals = app.basin_tree.item(children[2], "values")
        assert third_row_vals[0] == "Deriner Barajı"
        assert third_row_vals[1] == "Çoruh Havzası"
        assert third_row_vals[2] == "Çoruh Alt Havzası"

        # 2. Test cell editing with Turkish characters
        # Edit the first row's dam name
        app.rusle_view._edit_iid = children[0]
        app.rusle_view._edit_col_idx = 0
        app.rusle_view._cell_editor = tk.Entry(app.basin_tree)
        app.rusle_view._cell_editor.insert(0, "Güneydoğu Anadolu Atatürk Barajı")
        app.rusle_view._commit_cell_edit()

        edited_vals = app.basin_tree.item(children[0], "values")
        assert edited_vals[0] == "Güneydoğu Anadolu Atatürk Barajı"

        # 3. Set zonal statistics file and execute analysis
        app.rusle_view.zonal_file_var.set(str(zonal_csv))
        app.rusle_view.execute_rusle_analysis()

        # Verify results tree displays Turkish characters
        results_children = app.results_tree.get_children()
        assert len(results_children) == len(sample_turkish_data)

        first_res = app.results_tree.item(results_children[0], "values")
        assert first_res[0] == "Güneydoğu Anadolu Atatürk Barajı"
        assert first_res[1] == "Fırat Havzası"
        assert first_res[2] == "Aşağı Fırat Alt Havzası"

        third_res = app.results_tree.item(results_children[2], "values")
        assert third_res[0] == "Deriner Barajı"
        assert third_res[1] == "Çoruh Havzası"
        assert third_res[2] == "Çoruh Alt Havzası"

        # 4. Verify export contains Turkish characters
        export_path = tmp_path / "exported_results.csv"
        export_df = app.rusle_view._format_export_df()
        export_df.to_csv(export_path, index=False, encoding="utf-8-sig")

        re_read = read_table(str(export_path))
        assert "Dam" in re_read.columns
        assert re_read.iloc[0]["Dam"] == "Güneydoğu Anadolu Atatürk Barajı"
        assert re_read.iloc[2]["Dam"] == "Deriner Barajı"
        assert re_read.iloc[2]["Basin"] == "Çoruh Havzası"
        assert re_read.iloc[2]["Sub-Basin"] == "Çoruh Alt Havzası"

    finally:
        root.destroy()


def test_ui_with_turkish_column_headers(tmp_path, tk_root):
    tr_df = pd.DataFrame(
        {
            "Baraj Adı": ["Çınarcık Barajı", "Uğurlu Barajı"],
            "Havza Adı": ["Büyük Menderes Havzası", "Batı Akdeniz Havzası"],
            "Alt Havza Adı": ["Çine Alt Havzası", "Dalaman Alt Havzası"],
            "Alan (km2)": [850.0, 420.5],
            "Eğim": [0.025, 0.038],
        }
    )
    file_path = tmp_path / "turkish_headers.csv"
    tr_df.to_csv(file_path, index=False, encoding="utf-8-sig")

    root = tk.Toplevel(tk_root)
    try:
        app = SedimentApp(root)
        app.rusle_view._populate_basin_tree(str(file_path))

        children = app.basin_tree.get_children()
        assert len(children) == 2

        row1 = app.basin_tree.item(children[0], "values")
        assert row1[0] == "Çınarcık Barajı"
        assert row1[1] == "Büyük Menderes Havzası"
        assert row1[2] == "Çine Alt Havzası"
        assert float(row1[3]) == 850.0
        assert float(row1[4]) == 0.025

        row2 = app.basin_tree.item(children[1], "values")
        assert row2[0] == "Uğurlu Barajı"
        assert row2[1] == "Batı Akdeniz Havzası"
        assert row2[2] == "Dalaman Alt Havzası"
        assert float(row2[3]) == 420.5
        assert float(row2[4]) == 0.038
    finally:
        root.destroy()


def test_real_ankara_basin_with_turkish_characters_against_zonal_file(tmp_path, tk_root):
    basin_csv = tmp_path / "ankara_basins.csv"
    pd.DataFrame(
        {
            "Dam Name": ["Çamlıdere", "Kavşakkaya", "Çubuk 1", "Çubuk 2"],
            "Basin Name": ["Sakarya", "Sakarya", "Sakarya", "Sakarya"],
            "Sub-basin Name": [
                "Ankara Alt Havzası",
                "Ankara Alt Havzası",
                "Ankara Alt Havzası",
                "Ankara Alt Havzası",
            ],
            "Area": [754.2, 309.2, 834.7, 180.2],
            "Main Waterway Slope": [0.22, 0.23, 0.09, 0.16],
        }
    ).to_csv(basin_csv, index=False, encoding="utf-8-sig")

    root = tk.Toplevel(tk_root)
    try:
        app = SedimentApp(root)
        app.rusle_view._populate_basin_tree(str(basin_csv))

        # Check treeview items
        children = app.basin_tree.get_children()
        assert len(children) == 4
        assert app.basin_tree.item(children[0], "values")[0] == "Çamlıdere"
        assert app.basin_tree.item(children[1], "values")[0] == "Kavşakkaya"
        assert app.basin_tree.item(children[2], "values")[0] == "Çubuk 1"
        assert app.basin_tree.item(children[3], "values")[0] == "Çubuk 2"

        # Match against actual raw_zonal_means.csv (or raw_zonal_tables.csv)
        actual_zonal_path = (
            Path("inputs") / "raw_zonal_means.csv"
            if (Path("inputs") / "raw_zonal_means.csv").exists()
            else Path("inputs") / "raw_zonal_tables.csv"
        )
        app.rusle_view.zonal_file_var.set(str(actual_zonal_path.resolve()))
        app.rusle_view.execute_rusle_analysis()

        # Check results treeview items
        res_children = app.results_tree.get_children()
        assert len(res_children) == 4
        assert app.results_tree.item(res_children[0], "values")[0] == "Çamlıdere"
        assert app.results_tree.item(res_children[1], "values")[0] == "Kavşakkaya"
        assert app.results_tree.item(res_children[2], "values")[0] == "Çubuk 1"
        assert app.results_tree.item(res_children[3], "values")[0] == "Çubuk 2"
        # Verify calculated volume is positive
        assert float(app.results_tree.item(res_children[0], "values")[7]) > 0
    finally:
        root.destroy()
