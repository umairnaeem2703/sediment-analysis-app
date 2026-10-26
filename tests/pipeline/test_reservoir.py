"""P-M4-01: the reservoir curve of the sample dams (FR-M4-02), with the chart."""

from pathlib import Path

import pandas as pd
import pytest

from src.services.reporting import CURVE_PNG, reservoir_curve_figure, write_reservoir_curve
from src.services.reservoir import compute_dam_curve, write_reservoir_csv
from tests.samples import sample_curve_inputs

BENCHMARKS = Path(__file__).parents[1] / "benchmarks"
SAMPLE_DAMS = ["kavsakkaya", "cubuk_1", "cubuk_2"]


def _result(data, slug):
    dam = next(dam for dam in data.project.dams if dam.slug == slug)
    return compute_dam_curve(data.dam_sheet(dam).data, dam)


def test_p_m4_01_each_sample_dam_has_its_own_curve(tmp_path):
    data = sample_curve_inputs(tmp_path / "project")

    results = {slug: _result(data, slug) for slug in SAMPLE_DAMS}

    assert len({tuple(result.table["Volume_hm3"]) for result in results.values()}) == 3
    assert [len(results[slug].table) for slug in SAMPLE_DAMS] == [123, 43, 15]


def test_p_m4_01_the_curves_of_the_sheets_reproduce_the_worked_examples_of_b3_3(tmp_path):
    data = sample_curve_inputs(tmp_path / "project")

    kavsakkaya, cubuk_1, cubuk_2 = (_result(data, slug).curve for slug in SAMPLE_DAMS)

    assert kavsakkaya.h_min_m == pytest.approx(1088.86, abs=0.005)
    assert kavsakkaya.area(kavsakkaya.max_elev_m) == pytest.approx(4.09, abs=0.005)
    assert cubuk_1.h_min_m == pytest.approx(892.69, abs=0.005)
    assert cubuk_1.area(cubuk_1.max_elev_m) == pytest.approx(0.57, abs=0.005)
    assert cubuk_2.area(cubuk_2.max_elev_m) == pytest.approx(8.45, abs=0.005)


@pytest.mark.parametrize("slug", SAMPLE_DAMS)
def test_p_m4_01_each_curve_runs_from_the_bed_to_the_crest_through_hmax(tmp_path, slug):
    data = sample_curve_inputs(tmp_path / "project")
    dam = next(dam for dam in data.project.dams if dam.slug == slug)
    sheet = data.dam_sheet(dam).data

    table = _result(data, slug).table.set_index("Elevation_m")

    assert table.index[0] == sheet.bed_elev_m and table.index[-1] == sheet.crest_elev_m
    assert table["Volume_hm3"].iloc[0] == 0.0
    assert table["Volume_hm3"].iloc[-1] > sheet.max_vol_hm3


def test_p_m4_01_only_cubuk_2_is_flagged_as_too_shallow(tmp_path):
    data = sample_curve_inputs(tmp_path / "project")

    warnings = {slug: _result(data, slug).warnings for slug in SAMPLE_DAMS}

    assert warnings["kavsakkaya"] == [] and warnings["cubuk_1"] == []
    assert len(warnings["cubuk_2"]) == 1 and "5.3 m" in warnings["cubuk_2"][0]  # OI-01


@pytest.mark.parametrize("slug", SAMPLE_DAMS)
def test_p_m4_01_reservoir_curve_csv_matches_the_golden(tmp_path, slug):
    data = sample_curve_inputs(tmp_path / "project")

    path = write_reservoir_csv(_result(data, slug), tmp_path)

    written = pd.read_csv(path, encoding="utf-8-sig")
    golden = pd.read_csv(BENCHMARKS / f"reservoir_{slug}.csv", encoding="utf-8-sig")
    pd.testing.assert_frame_equal(written, golden, check_exact=False, rtol=1e-9, atol=0)


def test_p_m4_01_the_chart_shows_volume_and_area_against_the_level_and_marks_hmin_and_hmax(tmp_path):
    result = _result(sample_curve_inputs(tmp_path / "project"), "kavsakkaya")

    figure = reservoir_curve_figure(result)

    volume_axis, area_axis = figure.axes
    assert list(volume_axis.lines[0].get_xdata()) == list(result.table["Elevation_m"])
    assert list(volume_axis.lines[0].get_ydata()) == list(result.table["Volume_hm3"])
    assert list(area_axis.lines[0].get_ydata()) == list(result.table["Area_km2"])
    assert "m" in volume_axis.get_xlabel() and "hm³" in volume_axis.get_ylabel() and "km²" in area_axis.get_ylabel()
    marked = {line.get_label() for line in volume_axis.lines[1:]}
    assert {"Hmin", "Hmax"} <= marked


def test_p_m4_01_the_chart_is_written_as_a_png(tmp_path):
    result = _result(sample_curve_inputs(tmp_path / "project"), "cubuk_1")

    path = write_reservoir_curve(result, tmp_path)

    assert path == tmp_path / CURVE_PNG == tmp_path / "reservoir_curve.png"
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") and path.stat().st_size > 5_000
