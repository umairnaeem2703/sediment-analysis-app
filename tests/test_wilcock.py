import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from src.core.wilcock import (
    SECONDS_PER_YEAR,
    WATER_YEAR_COLUMN,
    BedloadVisualizer,
    FractionalModel,
    TimeSeriesAggregator,
)
from src.utils.paths import read_table, resource_path


def _model():
    df_frac = read_table(resource_path("inputs", "fractional_parameters.csv"))
    model = FractionalModel()
    model.load_fractional_parameters(df_frac)
    return model


def test_tau_ri_fallback_uses_wilcock_crowe():
    df_frac = read_table(resource_path("inputs", "fractional_parameters.csv"))
    df_no_tau = df_frac.drop(columns=["tau_ri"])
    model = FractionalModel()
    model.load_fractional_parameters(df_no_tau)

    tau_rm_star = 0.021 + 0.015 * math.exp(-20 * model.f_s)
    tau_rm = tau_rm_star * (model.s - 1) * model.rho_w * model.g * model.d50
    expected = []
    for d_i in df_no_tau["di"]:
        b = 0.67 / (1 + math.exp(1.5 - (d_i / model.d50)))
        expected.append(tau_rm * math.pow((d_i / model.d50), b))
    np.testing.assert_allclose(model._tau_ri, expected, rtol=1e-12, atol=1e-12)


def test_vectorized_matches_scalar_kernel():
    model = _model()
    flows = np.array([0.0, 12.5, 80.0, 250.0])
    vectorized = model.compute_transport_series(flows)
    scalar = np.array([model.compute_daily_fractional_transport(q) for q in flows])
    np.testing.assert_allclose(vectorized, scalar, rtol=1e-10, atol=1e-12)


def test_annual_summary_does_not_mutate_input():
    model = _model()
    df_flow = pd.DataFrame(
        {
            "Date": pd.date_range("2000-01-01", periods=3, freq="D"),
            "Flow": [10.0, 20.0, 30.0],
        }
    )
    original_cols = list(df_flow.columns)
    TimeSeriesAggregator(model).process_annual_averages(df_flow)
    assert list(df_flow.columns) == original_cols


def _water_year_flow():
    return pd.DataFrame(
        {"Date": ["30/09/2010", "01/10/2010"], "Flow": [10.0, 80.0], WATER_YEAR_COLUMN: [2010, 2011]}
    )


def test_water_year_column_drives_grouping():
    aggregator = TimeSeriesAggregator(_model())

    water = aggregator.process_annual_averages(_water_year_flow())
    calendar = aggregator.process_annual_averages(_water_year_flow().drop(columns=[WATER_YEAR_COLUMN]))

    assert water.index.name == WATER_YEAR_COLUMN
    assert list(water.index) == [2010, 2011]
    assert calendar.index.name == "Year"
    assert list(calendar.index) == [2010]


def test_missing_water_year_rows_are_dropped_with_warning():
    df_flow = _water_year_flow().astype({WATER_YEAR_COLUMN: object})
    df_flow.loc[1, WATER_YEAR_COLUMN] = None
    aggregator = TimeSeriesAggregator(_model())

    summary = aggregator.process_annual_averages(df_flow)

    assert list(summary.index) == [2010]
    assert any(WATER_YEAR_COLUMN in w for w in aggregator.warnings)


def test_phase3_handoff_keeps_water_year_key():
    aggregator = TimeSeriesAggregator(_model())
    handoff = aggregator.to_phase3_handoff(aggregator.process_annual_averages(_water_year_flow()))
    assert list(handoff.columns) == [WATER_YEAR_COLUMN, "Bedload_Volume_m3"]
    assert list(handoff[WATER_YEAR_COLUMN]) == [2010, 2011]


def test_summary_table_keeps_water_year_key():
    summary = TimeSeriesAggregator(_model()).process_annual_averages(_water_year_flow())
    table = BedloadVisualizer.prepare_summary_table(summary)
    assert list(table.columns)[0] == WATER_YEAR_COLUMN


@pytest.fixture()
def agg_backend():
    # Draw without a GUI. A TkAgg figure created before the session's Tk root exists
    # breaks later Tk-based tests on Windows, so restore the previous backend afterwards.
    previous = plt.get_backend()
    plt.switch_backend("Agg")
    yield
    plt.switch_backend(previous)


def test_trend_graph_labels_water_year_from_index_name(agg_backend):
    summary = TimeSeriesAggregator(_model()).process_annual_averages(_water_year_flow())
    calendar = TimeSeriesAggregator(_model()).process_annual_averages(
        _water_year_flow().drop(columns=[WATER_YEAR_COLUMN])
    )
    # Re-deriving the frame (which drops .attrs) must not lose the water-year label.
    rederived = summary.reset_index().set_index(WATER_YEAR_COLUMN)

    figures = [BedloadVisualizer().generate_trend_graph(df) for df in (summary, rederived, calendar)]
    try:
        labels = [fig.axes[0].get_xlabel() for fig in figures]
    finally:
        for fig in figures:
            plt.close(fig)
    assert labels == ["Water Year (Oct–Sep)", "Water Year (Oct–Sep)", "Year"]


def test_phase3_schema_and_volume_conversion():
    model = _model()
    df_flow = pd.DataFrame(
        {
            "Date": ["2010-01-01", "2010-06-01", "2011-01-01"],
            "Flow": [15.0, 25.0, 10.0],
        }
    )
    aggregator = TimeSeriesAggregator(model)
    annual = aggregator.process_annual_averages(df_flow)
    handoff = aggregator.to_phase3_handoff(annual)
    assert list(handoff.columns) == ["Year", "Bedload_Volume_m3"]
    mean_2010 = annual.loc[2010, "Annual_Average_Bedload"]
    vol_2010 = handoff.loc[handoff["Year"] == 2010, "Bedload_Volume_m3"].iloc[0]
    assert np.isclose(vol_2010, mean_2010 * model.bed_width * SECONDS_PER_YEAR)
