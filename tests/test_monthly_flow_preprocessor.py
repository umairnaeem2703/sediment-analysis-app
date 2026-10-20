import warnings

import numpy as np
import pandas as pd
import pytest

from src.core.monthly_flow_preprocessor import (
    HM3_TO_M3,
    SECONDS_PER_DAY,
    WATER_YEAR_COLUMN,
    MonthlyFlowPreprocessor,
    is_monthly_flow_table,
    main,
    prepare_daily_flow,
)
from src.core.wilcock import FractionalModel, TimeSeriesAggregator
from src.utils.paths import read_table, resource_path

TURKISH_HEADER = ["Yıllar", "Ekim", "Kasım", "Aralık", "Ocak", "Şubat", "Mart",
                  "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "TOP."]
ASCII_HEADER = ["Yillar", "Ekim", "Kasim", "Aralik", "Ocak", "Subat", "Mart",
                "Nisan", "Mayis", "Haziran", "Temmuz", "Agustos", "Eylul", "TOP."]


def _dsi_table(values_by_year, header=TURKISH_HEADER, summary_rows=True):
    """Build a wide DSI table: one row per water year plus TOP./ORT. summary rows."""
    rows = [[year, *vals, round(sum(vals), 2)] for year, vals in values_by_year.items()]
    if summary_rows:
        months = np.array([vals for vals in values_by_year.values()], dtype=float)
        rows.append(["TOP.", *months.sum(axis=0).round(2), round(months.sum(), 2)])
        rows.append(["ORT.", *months.mean(axis=0).round(2), round(months.sum(axis=1).mean(), 2)])
    return pd.DataFrame(rows, columns=header)


def _sample_values(years=(1974, 1975)):
    rng = np.random.default_rng(123)
    return {year: rng.uniform(0.0, 20.0, 12).round(2).tolist() for year in years}


def _model():
    df_frac = read_table(resource_path("inputs", "fractional_parameters.csv"))
    model = FractionalModel()
    model.load_fractional_parameters(df_frac)
    return model


# --- Parsing -------------------------------------------------------------------------


@pytest.mark.parametrize("header", [TURKISH_HEADER, ASCII_HEADER], ids=["turkish", "ascii"])
def test_parses_turkish_and_ascii_headers(header):
    values = _sample_values()
    monthly = MonthlyFlowPreprocessor().parse_table(_dsi_table(values, header=header))

    assert list(monthly.columns) == [WATER_YEAR_COLUMN, "Year", "Month", "Volume_hm3"]
    assert len(monthly) == 24
    for year, vals in values.items():
        got = monthly[monthly[WATER_YEAR_COLUMN] == year]["Volume_hm3"].sum()
        assert got == pytest.approx(sum(vals))


def test_summary_rows_and_total_column_are_dropped():
    monthly = MonthlyFlowPreprocessor().parse_table(_dsi_table(_sample_values()))
    assert set(monthly[WATER_YEAR_COLUMN]) == {1974, 1975}
    assert set(monthly["Month"]) == set(range(1, 13))


def test_missing_year_column_raises():
    df = _dsi_table(_sample_values()).rename(columns={"Yıllar": "Yil"})
    with pytest.raises(KeyError, match="Yıllar"):
        MonthlyFlowPreprocessor().parse_table(df)


def test_missing_month_column_raises():
    df = _dsi_table(_sample_values()).drop(columns=["Şubat"])
    with pytest.raises(KeyError, match="subat"):
        MonthlyFlowPreprocessor().parse_table(df)


@pytest.mark.parametrize("bad_value", [-1.0, None, "abc"], ids=["negative", "blank", "text"])
def test_invalid_volume_raises_with_location(bad_value):
    df = _dsi_table(_sample_values()).astype(object)
    df.loc[1, "Mart"] = bad_value
    with pytest.raises(ValueError, match="1975 Mart"):
        MonthlyFlowPreprocessor().parse_table(df)


def test_duplicate_year_raises():
    df = _dsi_table(_sample_values(), summary_rows=False)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        MonthlyFlowPreprocessor().parse_table(df)


def test_decimal_comma_values_are_accepted():
    df = _dsi_table({1974: [1.5] * 12}, summary_rows=False).astype(object)
    df.loc[0, "Ekim"] = "1,5"
    monthly = MonthlyFlowPreprocessor().parse_table(df)
    assert monthly["Volume_hm3"].tolist() == [1.5] * 12


@pytest.mark.parametrize("top_value", [999.0, None, "abc"], ids=["wrong", "blank", "text"])
def test_top_column_is_ignored(top_value):
    clean = _dsi_table(_sample_values(), summary_rows=False)
    df = clean.astype(object)
    df.loc[0, "TOP."] = top_value
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        monthly = MonthlyFlowPreprocessor().parse_table(df)
    pd.testing.assert_frame_equal(monthly, MonthlyFlowPreprocessor().parse_table(clean))


def test_row_with_volumes_but_no_year_raises():
    df = _dsi_table(_sample_values(), summary_rows=False).astype(object)
    df.loc[0, "Yıllar"] = None
    with pytest.raises(ValueError, match="no year label"):
        MonthlyFlowPreprocessor().parse_table(df)


def test_fully_blank_row_is_still_skipped():
    df = _dsi_table(_sample_values(), summary_rows=False).astype(object)
    df.loc[len(df)] = [None] * len(df.columns)
    monthly = MonthlyFlowPreprocessor().parse_table(df)
    assert set(monthly[WATER_YEAR_COLUMN]) == {1974, 1975}


def test_row_year_is_the_water_year_ending_in_september():
    df = _dsi_table({1974: [float(m) for m in range(1, 13)]}, summary_rows=False)
    monthly = MonthlyFlowPreprocessor().parse_table(df)

    assert set(monthly[WATER_YEAR_COLUMN]) == {1974}
    calendar = dict(zip(monthly["Month"], monthly["Year"]))
    assert calendar[10] == calendar[11] == calendar[12] == 1973  # Ekim-Aralık
    assert calendar[1] == calendar[9] == 1974  # Ocak-Eylül
    # Ekim is the first column of the row, so it carries the first value
    assert monthly.loc[monthly["Month"] == 10, "Volume_hm3"].iloc[0] == 1.0


def test_load_rejects_non_csv(tmp_path):
    with pytest.raises(ValueError, match="CSV"):
        MonthlyFlowPreprocessor().load(str(tmp_path / "flows.xlsx"))


# --- Disaggregation ------------------------------------------------------------------


def _monthly(values=None, **kwargs):
    pre = MonthlyFlowPreprocessor(**kwargs)
    return pre, pre.parse_table(_dsi_table(values or _sample_values(), summary_rows=False))


def test_mass_conservation_per_month():
    pre, monthly = _monthly()
    daily = pre.disaggregate(monthly)

    vol = daily.assign(Year=daily["Date"].dt.year, Month=daily["Date"].dt.month)
    vol["m3"] = vol["Flow"] * SECONDS_PER_DAY
    per_month = vol.groupby(["Year", "Month"])["m3"].sum()
    expected = monthly.set_index(["Year", "Month"])["Volume_hm3"] * HM3_TO_M3
    np.testing.assert_allclose(per_month.loc[expected.index], expected, rtol=1e-12, atol=1e-6)


def test_days_per_month_and_leap_february():
    # Water year 1976 ("end") runs Oct 1975 - Sep 1976 and contains Feb 1976 (leap).
    pre, monthly = _monthly({1976: [1.0] * 12})
    daily = pre.disaggregate(monthly)

    assert daily["Date"].iloc[0] == pd.Timestamp("1975-10-01")
    assert daily["Date"].iloc[-1] == pd.Timestamp("1976-09-30")
    assert len(daily) == 366
    assert (daily["Date"].diff().dropna() == pd.Timedelta(days=1)).all()
    assert (daily["Date"].dt.month == 2).sum() == 29


def test_daily_water_year_rolls_over_in_october():
    pre, monthly = _monthly({1974: [1.0] * 12, 1975: [1.0] * 12})
    water_year = pre.disaggregate(monthly).set_index("Date")[WATER_YEAR_COLUMN]

    assert water_year[pd.Timestamp("1973-10-01")] == 1974
    assert water_year[pd.Timestamp("1974-09-30")] == 1974
    assert water_year[pd.Timestamp("1974-10-01")] == 1975


def test_sigma_zero_is_uniform():
    pre, monthly = _monthly({1974: [3.0] * 12}, sigma=0.0)
    daily = pre.disaggregate(monthly)
    expected = 3.0 * HM3_TO_M3 / (daily["Date"].dt.days_in_month * SECONDS_PER_DAY)
    np.testing.assert_allclose(daily["Flow"], expected, rtol=1e-12)


def test_zero_volume_month_gives_zero_flow():
    values = {1974: [0.0] + [2.0] * 11}
    pre, monthly = _monthly(values)
    daily = pre.disaggregate(monthly)
    october = daily[daily["Date"].dt.month == 10]["Flow"]
    assert len(october) == 31
    assert (october == 0.0).all()
    assert not daily["Flow"].isna().any()


def test_lognormal_produces_peaks():
    pre, monthly = _monthly({1974: [10.0] * 12})
    daily = pre.disaggregate(monthly)
    ratio = daily.groupby(daily["Date"].dt.month)["Flow"].agg(lambda s: s.max() / s.mean())
    assert (ratio > 1.3).all()


def test_deterministic_for_same_seed():
    pre, monthly = _monthly(seed=7)
    pd.testing.assert_frame_equal(pre.disaggregate(monthly), MonthlyFlowPreprocessor(seed=7).disaggregate(monthly))


def test_different_seed_changes_series():
    _, monthly = _monthly()
    a = MonthlyFlowPreprocessor(seed=1).disaggregate(monthly)
    b = MonthlyFlowPreprocessor(seed=2).disaggregate(monthly)
    assert not np.allclose(a["Flow"], b["Flow"])


def test_month_seed_independent_of_other_years():
    values = _sample_values(years=(1974, 1975, 1976))
    pre = MonthlyFlowPreprocessor()
    full = pre.disaggregate(pre.parse_table(_dsi_table(values, summary_rows=False)))
    alone = pre.disaggregate(pre.parse_table(_dsi_table({1975: values[1975]}, summary_rows=False)))

    subset = full[full["Date"].isin(alone["Date"])].reset_index(drop=True)
    pd.testing.assert_frame_equal(subset, alone)


def test_output_schema():
    pre, monthly = _monthly()
    daily = pre.disaggregate(monthly)
    assert list(daily.columns) == ["Date", "Flow", WATER_YEAR_COLUMN]
    assert pd.api.types.is_datetime64_any_dtype(daily["Date"])
    assert pd.api.types.is_float_dtype(daily["Flow"])
    assert pd.api.types.is_integer_dtype(daily[WATER_YEAR_COLUMN])
    assert daily["Date"].is_monotonic_increasing
    assert not daily["Date"].duplicated().any()
    assert (daily["Flow"] >= 0).all()


@pytest.mark.parametrize("sigma", [-0.1, float("nan"), float("inf")], ids=["negative", "nan", "inf"])
def test_invalid_sigma_raises(sigma):
    with pytest.raises(ValueError, match="sigma"):
        MonthlyFlowPreprocessor(sigma=sigma)


@pytest.mark.parametrize("seed", [-1, -100])
def test_negative_seed_raises(seed):
    with pytest.raises(ValueError, match="seed"):
        MonthlyFlowPreprocessor(seed=seed)


@pytest.mark.parametrize("label", ["74", "19740", "1974.5", "Toplam"])
def test_unrecognised_year_label_raises(label):
    df = _dsi_table(_sample_values(), summary_rows=False)
    extra = df.iloc[[0]].copy()
    extra["Yıllar"] = label
    with pytest.raises(ValueError, match="Unrecognised year labels"):
        MonthlyFlowPreprocessor().parse_table(pd.concat([df, extra], ignore_index=True))


# --- Integration with the Wilcock & Crowe engine --------------------------------------


def test_output_feeds_time_series_aggregator():
    pre, monthly = _monthly()
    summary = TimeSeriesAggregator(_model()).process_annual_averages(pre.disaggregate(monthly))
    # The series carries Water_Year, so results are grouped by water year, not calendar year.
    assert summary.index.name == WATER_YEAR_COLUMN
    assert list(summary.index) == [1974, 1975]
    assert summary["Annual_Total_Bedload_m3_yr"].notna().all()


def test_lognormal_increases_bedload_vs_flat():
    values = {1974: [30.0] * 12}
    model = _model()
    flat_pre, monthly = _monthly(values, sigma=0.0)
    peaky_pre = MonthlyFlowPreprocessor(sigma=0.6)

    flat = model.compute_transport_series(flat_pre.disaggregate(monthly)["Flow"].to_numpy()).sum()
    peaky = model.compute_transport_series(peaky_pre.disaggregate(monthly)["Flow"].to_numpy()).sum()
    assert peaky > flat


def test_export_csv_roundtrip(tmp_path):
    pre, monthly = _monthly()
    daily = pre.disaggregate(monthly)
    out = tmp_path / "daily.csv"
    pre.export_csv(daily, str(out))

    reloaded = read_table(str(out))
    assert list(reloaded.columns) == ["Date", "Flow", WATER_YEAR_COLUMN]
    assert reloaded["Date"].iloc[0] == "01/10/1973"
    np.testing.assert_allclose(reloaded["Flow"], daily["Flow"], rtol=1e-12)

    # A CLI-exported CSV groups the same way as the direct DSI run.
    summary = TimeSeriesAggregator(_model()).process_annual_averages(reloaded)
    assert summary.index.name == WATER_YEAR_COLUMN
    assert list(summary.index) == [1974, 1975]


def test_cli_writes_daily_csv(tmp_path, capsys):
    src = tmp_path / "monthly.csv"
    _dsi_table(_sample_values()).to_csv(src, index=False, encoding="utf-8")
    out = tmp_path / "daily.csv"

    main([str(src), str(out), "--sigma", "0.4", "--seed", "3"])

    assert "Wrote 730 days" in capsys.readouterr().out
    written = read_table(str(out))
    assert len(written) == 730
    assert WATER_YEAR_COLUMN in written.columns


# --- GUI entry points ----------------------------------------------------------------


@pytest.mark.parametrize("header", [TURKISH_HEADER, ASCII_HEADER], ids=["turkish", "ascii"])
def test_is_monthly_flow_table_detects_dsi_headers(header):
    assert is_monthly_flow_table(_dsi_table(_sample_values(), header=header))


def test_is_monthly_flow_table_routes_malformed_dsi_table():
    df = _dsi_table(_sample_values()).drop(columns=["Şubat"])
    assert is_monthly_flow_table(df)


def test_is_monthly_flow_table_rejects_daily_series():
    assert not is_monthly_flow_table(read_table(resource_path("inputs", "daily_flow_data.csv")))


def test_prepare_daily_flow_matches_disaggregate_and_reports_conversion():
    df = _dsi_table(_sample_values(), summary_rows=False)
    pre = MonthlyFlowPreprocessor()

    daily, notes = prepare_daily_flow(df)

    pd.testing.assert_frame_equal(daily, pre.disaggregate(pre.parse_table(df)))
    assert len(notes) == 1
    assert "2 water years" in notes[0]


# --- Sample DSI data -----------------------------------------------------------------


@pytest.mark.parametrize("name", ["cubuk_1_flow.csv", "cubuk_2_flow.csv", "kavsakkaya_flow.csv"])
def test_sample_dam_files_give_water_year_bedload_curve(name):
    raw = read_table(str(resource_path("inputs", "dam_flow_data", name)))
    assert is_monthly_flow_table(raw)

    daily, _ = prepare_daily_flow(raw)
    summary = TimeSeriesAggregator(_model()).process_annual_averages(daily)

    assert summary.index.name == WATER_YEAR_COLUMN
    assert list(summary.index) == list(range(1974, 2013))
    bedload = summary["Annual_Total_Bedload_m3_yr"]
    assert np.isfinite(bedload).all() and (bedload >= 0).all()
    assert (bedload > 0).any()


@pytest.mark.parametrize("name", ["cubuk_1_flow.csv", "cubuk_2_flow.csv", "kavsakkaya_flow.csv"])
def test_parses_sample_dam_flow_files(name):
    path = resource_path("inputs", "dam_flow_data", name)
    raw = read_table(str(path))
    monthly = MonthlyFlowPreprocessor().load(str(path))

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
