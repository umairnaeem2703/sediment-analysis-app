"""C-M3-02: flow files on disk. A DSİ monthly CSV is read and a synthetic daily series is written back (FR-M3-01)."""

import numpy as np
import pandas as pd
import pytest

from src.core.monthly_flow_preprocessor import MonthlyFlowPreprocessor, prepare_daily_flow
from src.core.wilcock import WATER_YEAR_COLUMN, TimeSeriesAggregator
from src.services.flow_files import export_daily_csv, load_monthly_flow, main
from src.services.labels import is_monthly_flow_table
from src.utils.paths import read_table, resource_path
from tests.flows import dsi_table, sample_values
from tests.samples import sample_fraction_model


def test_c_m3_02_load_rejects_non_csv(tmp_path):
    with pytest.raises(ValueError, match="CSV"):
        load_monthly_flow(str(tmp_path / "flows.xlsx"))


def test_c_m3_02_export_csv_roundtrip(tmp_path):
    pre = MonthlyFlowPreprocessor()
    daily = pre.disaggregate(pre.parse_table(dsi_table(sample_values(), summary_rows=False)))
    out = tmp_path / "daily.csv"
    export_daily_csv(daily, str(out))

    reloaded = read_table(str(out))
    assert list(reloaded.columns) == ["Date", "Flow Q (m3/s)", WATER_YEAR_COLUMN]
    assert reloaded["Date"].iloc[0] == "01/10/1973"
    np.testing.assert_allclose(reloaded["Flow Q (m3/s)"], daily["Flow Q (m3/s)"], rtol=1e-12)

    # A CLI-exported CSV groups the same way as the direct DSI run.
    summary = TimeSeriesAggregator(sample_fraction_model()).process_annual_averages(reloaded)
    assert summary.index.name == WATER_YEAR_COLUMN
    assert list(summary.index) == [1974, 1975]


def test_c_m3_02_cli_writes_daily_csv(tmp_path, capsys):
    src = tmp_path / "monthly.csv"
    dsi_table(sample_values()).to_csv(src, index=False, encoding="utf-8")
    out = tmp_path / "daily.csv"

    main([str(src), str(out), "--sigma", "0.4", "--seed", "3"])

    assert "Wrote 730 days" in capsys.readouterr().out
    written = read_table(str(out))
    assert len(written) == 730
    assert WATER_YEAR_COLUMN in written.columns


@pytest.mark.parametrize("name", ["cubuk_1_flow.csv", "cubuk_2_flow.csv", "kavsakkaya_flow.csv"])
def test_c_m3_02_sample_dam_files_give_water_year_bedload_curve(name):
    raw = read_table(str(resource_path("inputs", "dam_flow_data", name)))
    assert is_monthly_flow_table(raw)

    daily, _ = prepare_daily_flow(raw)
    summary = TimeSeriesAggregator(sample_fraction_model()).process_annual_averages(daily)

    assert summary.index.name == WATER_YEAR_COLUMN
    assert list(summary.index) == list(range(1974, 2013))
    bedload = summary["Annual_Total_Bedload_m3_yr"]
    assert np.isfinite(bedload).all() and (bedload >= 0).all()
    assert (bedload > 0).any()


@pytest.mark.parametrize("name", ["cubuk_1_flow.csv", "cubuk_2_flow.csv", "kavsakkaya_flow.csv"])
def test_c_m3_02_parses_sample_dam_flow_files(name):
    path = resource_path("inputs", "dam_flow_data", name)
    raw = read_table(str(path))
    monthly = load_monthly_flow(str(path))

    assert monthly[WATER_YEAR_COLUMN].min() == 1974
    assert monthly[WATER_YEAR_COLUMN].max() == 2012
    assert len(monthly) == 39 * 12

    # The engine ignores TOP./ORT.; this checks the sample data against its own TOP. column.
    years = pd.to_numeric(raw.iloc[:, 0], errors="coerce")
    data = raw[years.notna()]
    totals = data.set_index(years[years.notna()].astype(int))["TOP."].astype(float)
    annual = monthly.groupby(WATER_YEAR_COLUMN)["Volume_hm3"].sum()
    assert len(totals) == 39
    np.testing.assert_allclose(annual.loc[totals.index].to_numpy(), totals.to_numpy(), atol=0.05)


def test_c_m3_02_cli_takes_the_lag_1_phi(tmp_path):
    src = tmp_path / "monthly.csv"
    dsi_table(sample_values()).to_csv(src, index=False, encoding="utf-8")
    flat, persistent = tmp_path / "flat.csv", tmp_path / "persistent.csv"

    main([str(src), str(flat), "--seed", "3"])
    main([str(src), str(persistent), "--seed", "3", "--phi", "0.8"])

    assert not np.allclose(read_table(str(flat))["Flow Q (m3/s)"], read_table(str(persistent))["Flow Q (m3/s)"])
    with pytest.raises(ValueError, match="phi"):
        main([str(src), str(tmp_path / "bad.csv"), "--phi", "1"])
