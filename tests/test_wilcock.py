import numpy as np
import pandas as pd

from paths import read_table, resource_path
from wilcock_engine import FractionalModel, TimeSeriesAggregator, SECONDS_PER_YEAR


def _model():
    df_frac = read_table(resource_path("inputs", "fractional_parameters.csv"))
    model = FractionalModel()
    model.load_fractional_parameters(df_frac)
    return model


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
