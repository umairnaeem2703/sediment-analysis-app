"""P-M3-01: the bedload summary table and trend chart, now in the reporting service (FR-M3-05)."""

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from src.core.wilcock import WATER_YEAR_COLUMN, TimeSeriesAggregator
from src.services.reporting import BedloadVisualizer
from tests.samples import sample_fraction_model


def _water_year_flow() -> pd.DataFrame:
    return pd.DataFrame({"Date": ["30/09/2010", "01/10/2010"], "Flow": [10.0, 80.0], WATER_YEAR_COLUMN: [2010, 2011]})


@pytest.fixture()
def agg_backend():
    # Draw without a GUI. A TkAgg figure created before the session's Tk root exists
    # breaks later Tk-based tests on Windows, so restore the previous backend afterwards.
    previous = plt.get_backend()
    plt.switch_backend("Agg")
    yield
    plt.switch_backend(previous)


def test_p_m3_01_the_summary_table_keeps_the_water_year_key():
    summary = TimeSeriesAggregator(sample_fraction_model()).process_annual_averages(_water_year_flow())

    table = BedloadVisualizer.prepare_summary_table(summary)

    assert list(table.columns)[0] == WATER_YEAR_COLUMN


def test_p_m3_01_the_trend_chart_labels_water_years_from_the_index_name(agg_backend):
    aggregator = TimeSeriesAggregator(sample_fraction_model())
    summary = aggregator.process_annual_averages(_water_year_flow())
    calendar = aggregator.process_annual_averages(_water_year_flow().drop(columns=[WATER_YEAR_COLUMN]))
    # Re-deriving the frame (which drops .attrs) must not lose the water-year label.
    rederived = summary.reset_index().set_index(WATER_YEAR_COLUMN)

    figures = [BedloadVisualizer().generate_trend_graph(df) for df in (summary, rederived, calendar)]
    try:
        labels = [fig.axes[0].get_xlabel() for fig in figures]
    finally:
        for fig in figures:
            plt.close(fig)

    assert labels == ["Water Year (Oct–Sep)", "Water Year (Oct–Sep)", "Year"]
