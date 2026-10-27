"""P-M3-01: the bedload trend chart (FR-M3-05)."""

import pandas as pd
import pytest
from matplotlib.figure import Figure

from src.services.bedload import FlowSeries, compute_bedload
from src.services.reporting import TREND_PNG, bedload_trend_figure, write_bedload_trend
from tests.samples import sample_fraction_model


def _table(water_year: bool) -> pd.DataFrame:
    flow = pd.DataFrame({"Date": ["30/09/2010", "01/10/2010"], "Flow Q (m3/s)": [10.0, 80.0]})
    if water_year:
        flow["Water_Year"] = [2010, 2011]
    fractions = pd.DataFrame(sample_fraction_model().fractions)[["di", "Fi"]]
    return compute_bedload(FlowSeries(flow, False, []), fractions).table


def test_p_m3_01_the_chart_labels_water_years_and_calendar_years_by_the_key_column():
    water, calendar = bedload_trend_figure(_table(True)), bedload_trend_figure(_table(False))

    assert water.axes[0].get_xlabel() == "Water Year (Oct–Sep)"
    assert calendar.axes[0].get_xlabel() == "Year"


def test_p_m3_01_the_chart_plots_the_flow_and_the_mass_of_every_year():
    table = _table(True)

    figure = bedload_trend_figure(table)

    assert isinstance(figure, Figure) and len(figure.axes) == 2
    flow_axis, mass_axis = figure.axes
    assert list(flow_axis.lines[0].get_ydata()) == list(table["Mean_Flow_m3_s"])
    assert list(mass_axis.lines[0].get_ydata()) == list(table["Mass_t_yr"])
    assert list(flow_axis.lines[0].get_xdata()) == [2010, 2011]


def test_p_m3_01_an_empty_table_is_an_error():
    with pytest.raises(ValueError, match="empty"):
        bedload_trend_figure(_table(True).iloc[0:0])


def test_p_m3_01_the_chart_is_written_as_a_png(tmp_path):
    path = write_bedload_trend(_table(True), tmp_path)

    assert path == tmp_path / TREND_PNG == tmp_path / "bedload_trend.png"
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") and path.stat().st_size > 5_000
