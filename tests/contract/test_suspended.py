"""C-M2-01: the suspended service's contract with its inputs and its output file (FR-M2-01, FR-M2-04, FR-X-03)."""

import pandas as pd
import pytest

from src.services.regional import AREA, DAM, SLOPE, SUBBASIN
from src.services.suspended import compute_suspended, write_suspended_csv


def _basins(*rows, dam="Test Dam"):
    frame = pd.DataFrame(rows, columns=[SUBBASIN, AREA, SLOPE])
    frame.insert(0, DAM, dam)
    return frame


def _zonal(*rows):
    return pd.DataFrame(rows, columns=[SUBBASIN, "MEAN"])


def test_c_m2_01_turkish_and_ascii_spellings_meet_without_a_warning():
    result = compute_suspended(
        _basins(("Aşağı Sakarya Alt Havzası", 100.0, 0.1)), _zonal(("Asagi sakarya Alt Havzası", 3.23))
    )

    assert list(result.table["Zonal_Mean_t_ha_yr"]) == [3.23]
    assert result.warnings == []


def test_c_m2_01_a_loose_match_is_used_and_listed_in_the_warnings():
    result = compute_suspended(_basins(("Sakarya Alt Havzası", 100.0, 0.1)), _zonal(("Orta Sakarya Alt Havzası", 2.5)))

    assert list(result.table["Zonal_Mean_t_ha_yr"]) == [2.5]
    assert len(result.warnings) == 1
    assert "Sakarya Alt Havzası" in result.warnings[0] and "loosely" in result.warnings[0]
    assert "'Orta Sakarya Alt Havzası'" in result.warnings[0]  # the zonal file's own spelling


def test_c_m2_01_a_missing_match_is_an_error_naming_the_sub_basin_and_the_file():
    with pytest.raises(ValueError) as error:
        compute_suspended(
            _basins(("Ankara Alt Havzası", 10.0, 0.1), ("Konya Alt Havzası", 20.0, 0.1)),
            _zonal(("Ankara Alt Havzası", 3.1)),
            "raw_zonal_means.csv",
        )

    assert "Konya Alt Havzası" in str(error.value) and "raw_zonal_means.csv" in str(error.value)
    assert "Ankara" not in str(error.value)


def test_c_m2_01_an_ambiguous_match_is_an_error_naming_the_sub_basin():
    with pytest.raises(ValueError) as error:
        compute_suspended(
            _basins(("Sakarya Alt Havzası", 10.0, 0.1)),
            _zonal(("Orta Sakarya Alt Havzası", 2.5), ("Asagi Sakarya Alt Havzası", 3.2)),
        )

    assert "Sakarya Alt Havzası" in str(error.value) and "ambiguous" in str(error.value)


def test_c_m2_01_a_negative_zonal_mean_is_an_error_naming_the_sub_basin():
    with pytest.raises(ValueError, match="Ankara Alt Havzası"):
        compute_suspended(_basins(("Ankara Alt Havzası", 10.0, 0.1)), _zonal(("Ankara Alt Havzası", -1.0)))


def test_c_m2_01_the_csv_holds_a_row_per_sub_basin_and_a_total_row(tmp_path):
    result = compute_suspended(
        _basins(("Ankara Alt Havzası", 10.0, 0.1), ("Göksu Alt Havzası", 20.0, 0.2)),
        _zonal(("Ankara Alt Havzası", 3.0), ("Göksu Alt Havzası", 2.0)),
    )

    path = write_suspended_csv(result, tmp_path)

    assert path == tmp_path / "suspended.csv"
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # UTF-8 with BOM, so Excel shows the Turkish letters
    written = pd.read_csv(path, encoding="utf-8-sig")
    assert list(written[SUBBASIN]) == ["Ankara Alt Havzası", "Göksu Alt Havzası", "Total"]
    assert written["Volume_m3"].iloc[2] == pytest.approx(result.total_volume_m3, rel=1e-12)
    assert written["Area_km2"].iloc[2] == pytest.approx(30.0)
    assert pd.isna(written["SIO_Average"].iloc[2])


def test_c_m2_01_a_zonal_name_listed_twice_with_different_values_is_not_used():
    with pytest.raises(ValueError, match="Ankara Alt Havzası"):
        compute_suspended(
            _basins(("Ankara Alt Havzası", 10.0, 0.1)),
            _zonal(("Ankara Alt Havzası", 3.1), ("Ankara Alt Havzası", 9.9)),
        )


def test_c_m2_01_a_zonal_name_listed_twice_with_one_value_is_used():
    result = compute_suspended(
        _basins(("Ankara Alt Havzası", 10.0, 0.1)), _zonal(("Ankara Alt Havzası", 3.1), ("Ankara Alt Havzası", 3.1))
    )

    assert list(result.table["Zonal_Mean_t_ha_yr"]) == [3.1]


def test_c_m2_01_two_zonal_entries_that_collide_on_a_name_are_ambiguous_not_the_last_row():
    with pytest.raises(ValueError, match="Havza 1"):
        compute_suspended(_basins(("Havza 1", 10.0, 0.1)), _zonal(("Kuzey Havza 1", 1.0), ("Guney Havza 1", 7.0)))


def test_c_m2_01_rows_of_more_than_one_dam_are_refused():
    first, second = (
        _basins(("Ankara Alt Havzası", 10.0, 0.1), dam="Dam A"),
        _basins(("Göksu Alt Havzası", 5.0, 0.2), dam="Dam B"),
    )

    with pytest.raises(ValueError, match="one dam at a time"):
        compute_suspended(pd.concat([first, second]), _zonal(("Ankara Alt Havzası", 3.1), ("Göksu Alt Havzası", 2.8)))
