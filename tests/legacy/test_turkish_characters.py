import pandas as pd
import pytest

from src.core.rusle import (
    ZonalMatcher,
    find_basin_table_columns,
    normalize_header,
    to_ascii_turkish,
    turkish_lower,
)
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
