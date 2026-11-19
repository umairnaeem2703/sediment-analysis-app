"""P-M4-01: the measured reservoir curve of the sample dams (FR-M4-02, D75), with the chart."""

from pathlib import Path

import pandas as pd
import pytest

from src.services.reporting import CURVE_PNG, reservoir_curve_figure, write_reservoir_curve
from src.services.reservoir import compute_dam_curve, import_curve_sheet, write_reservoir_csv
from tests.samples import CURVE_DAMS, sample_curve, sample_curve_inputs, sample_regional, sample_sheet

BENCHMARKS = Path(__file__).parents[1] / "benchmarks"


def _dam(data, slug):
    return next(dam for dam in data.project.dams if dam.slug == slug)


def _result(data, slug="kavsakkaya"):
    dam = _dam(data, slug)
    return compute_dam_curve(data.project, data.dam_sheet(dam).data, dam)


def test_p_m4_01_the_kavsakkaya_curve_is_its_curve_sheet_with_hmin_read_from_it(tmp_path):
    result = _result(sample_curve_inputs(tmp_path / "project"))

    assert len(result.table) == 69 and result.warnings == []
    assert result.curve.h_min_m == pytest.approx(1086.27, abs=0.005)  # Vdead = 90.57 - 74.1 hm3 (provisional, OI-11)
    assert result.curve.volume(1099.0) == pytest.approx(33.861)  # the sheet has no row at 1099 m


def test_p_m4_01_the_sample_dam_sheet_of_kavsakkaya_is_refused_against_its_curve(tmp_path):
    """OI-11: until the hydrologist corrects one of the two files, the real sample sheet does not agree."""
    data = sample_regional(tmp_path / "project")
    data.import_dam_sheets([str(sample_sheet("kavsakkaya"))])
    dam = _dam(data, "kavsakkaya")
    import_curve_sheet(data.project, dam, sample_curve("kavsakkaya"))

    with pytest.raises(ValueError, match="cannot be used") as raised:
        _result(data)

    assert "Hbed on the dam sheet (1063 m)" in str(raised.value)
    assert "Vmax on the dam sheet (80.8 hm³)" in str(raised.value)


def test_p_m4_01_a_dam_without_a_curve_sheet_has_no_curve(tmp_path):
    with pytest.raises(ValueError, match="Çubuk 1 has no reservoir curve sheet"):
        _result(sample_curve_inputs(tmp_path / "project"), "cubuk_1")


@pytest.mark.parametrize("slug", CURVE_DAMS)
def test_p_m4_01_reservoir_curve_csv_matches_the_golden(tmp_path, slug):
    data = sample_curve_inputs(tmp_path / "project")

    path = write_reservoir_csv(_result(data, slug), tmp_path)

    written = pd.read_csv(path, encoding="utf-8-sig")
    golden = pd.read_csv(BENCHMARKS / f"reservoir_{slug}.csv", encoding="utf-8-sig")
    pd.testing.assert_frame_equal(written, golden, check_exact=False, rtol=1e-9, atol=0)


def test_p_m4_01_the_chart_shows_volume_and_area_against_the_level_and_marks_hmin_and_hmax(tmp_path):
    result = _result(sample_curve_inputs(tmp_path / "project"))

    figure = reservoir_curve_figure(result)

    volume_axis, area_axis = figure.axes
    assert list(volume_axis.lines[0].get_xdata()) == list(result.table["Elevation_m"])
    assert list(volume_axis.lines[0].get_ydata()) == list(result.table["Volume_hm3"])
    assert list(area_axis.lines[0].get_ydata()) == list(result.table["Area_km2"])
    assert "m" in volume_axis.get_xlabel() and "hm³" in volume_axis.get_ylabel() and "km²" in area_axis.get_ylabel()
    marked = {line.get_label() for line in volume_axis.lines[1:]}
    assert {"Hmin", "Hmax"} <= marked


def test_p_m4_01_the_chart_is_written_as_a_png(tmp_path):
    result = _result(sample_curve_inputs(tmp_path / "project"))

    path = write_reservoir_curve(result, tmp_path)

    assert path == tmp_path / CURVE_PNG == tmp_path / "reservoir_curve.png"
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") and path.stat().st_size > 5_000
