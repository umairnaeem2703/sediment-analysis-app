"""U-M3-01: the DSİ monthly table and its conversion to daily flow (FR-M3-01, B3.2 monthly-to-daily, D10)."""

import warnings

import numpy as np
import pandas as pd
import pytest

from src.core.monthly_flow_preprocessor import (
    DEFAULT_PHI,
    HM3_TO_M3,
    MAX_SIGMA,
    SECONDS_PER_DAY,
    WATER_YEAR_COLUMN,
    MonthlyFlowPreprocessor,
    prepare_daily_flow,
)
from src.core.wilcock import TimeSeriesAggregator
from src.services.labels import is_monthly_flow_table
from tests.flows import ASCII_HEADER, TURKISH_HEADER, dsi_table, sample_values
from tests.samples import sample_fraction_model


def _monthly(values=None, **kwargs):
    pre = MonthlyFlowPreprocessor(**kwargs)
    return pre, pre.parse_table(dsi_table(values or sample_values(), summary_rows=False))


def test_u_m3_01_parses_the_dsi_table():
    values = sample_values()
    monthly = MonthlyFlowPreprocessor().parse_table(dsi_table(values))

    assert list(monthly.columns) == [WATER_YEAR_COLUMN, "Year", "Month", "Volume_hm3"]
    assert len(monthly) == 24
    for year, vals in values.items():
        got = monthly[monthly[WATER_YEAR_COLUMN] == year]["Volume_hm3"].sum()
        assert got == pytest.approx(sum(vals))


def test_u_m3_01_summary_rows_and_total_column_are_dropped():
    monthly = MonthlyFlowPreprocessor().parse_table(dsi_table(sample_values()))
    assert set(monthly[WATER_YEAR_COLUMN]) == {1974, 1975}
    assert set(monthly["Month"]) == set(range(1, 13))


def test_u_m3_01_missing_year_column_raises():
    df = dsi_table(sample_values()).rename(columns={"Yıllar": "Yil"})
    with pytest.raises(KeyError, match="Yıllar"):
        MonthlyFlowPreprocessor().parse_table(df)


def test_u_m3_01_missing_month_column_raises():
    df = dsi_table(sample_values()).drop(columns=["Şubat"])
    with pytest.raises(KeyError, match="Şubat"):
        MonthlyFlowPreprocessor().parse_table(df)


@pytest.mark.parametrize("bad_value", [-1.0, None, "abc"], ids=["negative", "blank", "text"])
def test_u_m3_01_invalid_volume_raises_with_location(bad_value):
    df = dsi_table(sample_values()).astype(object)
    df.loc[1, "Mart"] = bad_value
    with pytest.raises(ValueError, match="1975 Mart"):
        MonthlyFlowPreprocessor().parse_table(df)


def test_u_m3_01_duplicate_year_raises():
    df = dsi_table(sample_values(), summary_rows=False)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        MonthlyFlowPreprocessor().parse_table(df)


def test_u_m3_01_decimal_comma_values_are_refused():
    df = dsi_table({1974: [1.5] * 12}, summary_rows=False).astype(object)
    df.loc[0, "Ekim"] = "1,5"
    with pytest.raises(ValueError, match="1974 Ekim"):
        MonthlyFlowPreprocessor().parse_table(df)


@pytest.mark.parametrize("top_value", [999.0, None, "abc"], ids=["wrong", "blank", "text"])
def test_u_m3_01_top_column_is_ignored(top_value):
    clean = dsi_table(sample_values(), summary_rows=False)
    df = clean.astype(object)
    df.loc[0, "TOP."] = top_value
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        monthly = MonthlyFlowPreprocessor().parse_table(df)
    pd.testing.assert_frame_equal(monthly, MonthlyFlowPreprocessor().parse_table(clean))


def test_u_m3_01_row_with_volumes_but_no_year_raises():
    df = dsi_table(sample_values(), summary_rows=False).astype(object)
    df.loc[0, "Yıllar"] = None
    with pytest.raises(ValueError, match="no year label"):
        MonthlyFlowPreprocessor().parse_table(df)


def test_u_m3_01_fully_blank_row_is_still_skipped():
    df = dsi_table(sample_values(), summary_rows=False).astype(object)
    df.loc[len(df)] = [None] * len(df.columns)
    monthly = MonthlyFlowPreprocessor().parse_table(df)
    assert set(monthly[WATER_YEAR_COLUMN]) == {1974, 1975}


def test_u_m3_01_row_year_is_the_water_year_ending_in_september():
    df = dsi_table({1974: [float(m) for m in range(1, 13)]}, summary_rows=False)
    monthly = MonthlyFlowPreprocessor().parse_table(df)

    assert set(monthly[WATER_YEAR_COLUMN]) == {1974}
    calendar = dict(zip(monthly["Month"], monthly["Year"], strict=True))
    assert calendar[10] == calendar[11] == calendar[12] == 1973  # Ekim-Aralık
    assert calendar[1] == calendar[9] == 1974  # Ocak-Eylül
    # Ekim is the first column of the row, so it carries the first value
    assert monthly.loc[monthly["Month"] == 10, "Volume_hm3"].iloc[0] == 1.0


def test_u_m3_01_mass_conservation_per_month():
    pre, monthly = _monthly()
    daily = pre.disaggregate(monthly)

    vol = daily.assign(Year=daily["Date"].dt.year, Month=daily["Date"].dt.month)
    vol["m3"] = vol["Flow Q (m3/s)"] * SECONDS_PER_DAY
    per_month = vol.groupby(["Year", "Month"])["m3"].sum()
    expected = monthly.set_index(["Year", "Month"])["Volume_hm3"] * HM3_TO_M3
    np.testing.assert_allclose(per_month.loc[expected.index], expected, rtol=1e-12, atol=1e-6)


def test_u_m3_01_days_per_month_and_leap_february():
    # Water year 1976 ("end") runs Oct 1975 - Sep 1976 and contains Feb 1976 (leap).
    pre, monthly = _monthly({1976: [1.0] * 12})
    daily = pre.disaggregate(monthly)

    assert daily["Date"].iloc[0] == pd.Timestamp("1975-10-01")
    assert daily["Date"].iloc[-1] == pd.Timestamp("1976-09-30")
    assert len(daily) == 366
    assert (daily["Date"].diff().dropna() == pd.Timedelta(days=1)).all()
    assert (daily["Date"].dt.month == 2).sum() == 29


def test_u_m3_01_daily_water_year_rolls_over_in_october():
    pre, monthly = _monthly({1974: [1.0] * 12, 1975: [1.0] * 12})
    water_year = pre.disaggregate(monthly).set_index("Date")[WATER_YEAR_COLUMN]

    assert water_year[pd.Timestamp("1973-10-01")] == 1974
    assert water_year[pd.Timestamp("1974-09-30")] == 1974
    assert water_year[pd.Timestamp("1974-10-01")] == 1975


def test_u_m3_01_sigma_zero_is_uniform():
    pre, monthly = _monthly({1974: [3.0] * 12}, sigma=0.0)
    daily = pre.disaggregate(monthly)
    expected = 3.0 * HM3_TO_M3 / (daily["Date"].dt.days_in_month * SECONDS_PER_DAY)
    np.testing.assert_allclose(daily["Flow Q (m3/s)"], expected, rtol=1e-12)


def test_u_m3_01_zero_volume_month_gives_zero_flow():
    values = {1974: [0.0] + [2.0] * 11}
    pre, monthly = _monthly(values)
    daily = pre.disaggregate(monthly)
    october = daily[daily["Date"].dt.month == 10]["Flow Q (m3/s)"]
    assert len(october) == 31
    assert (october == 0.0).all()
    assert not daily["Flow Q (m3/s)"].isna().any()


def test_u_m3_01_lognormal_produces_peaks():
    pre, monthly = _monthly({1974: [10.0] * 12})
    daily = pre.disaggregate(monthly)
    ratio = daily.groupby(daily["Date"].dt.month)["Flow Q (m3/s)"].agg(lambda s: s.max() / s.mean())
    assert (ratio > 1.3).all()


def test_u_m3_01_deterministic_for_same_seed():
    pre, monthly = _monthly(seed=7)
    pd.testing.assert_frame_equal(pre.disaggregate(monthly), MonthlyFlowPreprocessor(seed=7).disaggregate(monthly))


def test_u_m3_01_different_seed_changes_series():
    _, monthly = _monthly()
    a = MonthlyFlowPreprocessor(seed=1).disaggregate(monthly)
    b = MonthlyFlowPreprocessor(seed=2).disaggregate(monthly)
    assert not np.allclose(a["Flow Q (m3/s)"], b["Flow Q (m3/s)"])


def test_u_m3_01_month_seed_independent_of_other_years():
    values = sample_values(years=(1974, 1975, 1976))
    pre = MonthlyFlowPreprocessor()
    full = pre.disaggregate(pre.parse_table(dsi_table(values, summary_rows=False)))
    alone = pre.disaggregate(pre.parse_table(dsi_table({1975: values[1975]}, summary_rows=False)))

    subset = full[full["Date"].isin(alone["Date"])].reset_index(drop=True)
    pd.testing.assert_frame_equal(subset, alone)


def test_u_m3_01_output_schema():
    pre, monthly = _monthly()
    daily = pre.disaggregate(monthly)
    assert list(daily.columns) == ["Date", "Flow Q (m3/s)", WATER_YEAR_COLUMN]
    assert pd.api.types.is_datetime64_any_dtype(daily["Date"])
    assert pd.api.types.is_float_dtype(daily["Flow Q (m3/s)"])
    assert pd.api.types.is_integer_dtype(daily[WATER_YEAR_COLUMN])
    assert daily["Date"].is_monotonic_increasing
    assert not daily["Date"].duplicated().any()
    assert (daily["Flow Q (m3/s)"] >= 0).all()


@pytest.mark.parametrize("sigma", [-0.1, float("nan"), float("inf")], ids=["negative", "nan", "inf"])
def test_u_m3_01_invalid_sigma_raises(sigma):
    with pytest.raises(ValueError, match="sigma"):
        MonthlyFlowPreprocessor(sigma=sigma)


@pytest.mark.parametrize("seed", [-1, -100])
def test_u_m3_01_negative_seed_raises(seed):
    with pytest.raises(ValueError, match="seed"):
        MonthlyFlowPreprocessor(seed=seed)


@pytest.mark.parametrize("label", ["74", "19740", "1974.5", "Toplam"])
def test_u_m3_01_unrecognised_year_label_raises(label):
    df = dsi_table(sample_values(), summary_rows=False)
    extra = df.iloc[[0]].copy()
    extra["Yıllar"] = label
    with pytest.raises(ValueError, match="Unrecognised year labels"):
        MonthlyFlowPreprocessor().parse_table(pd.concat([df, extra], ignore_index=True))


def test_u_m3_01_output_feeds_time_series_aggregator():
    pre, monthly = _monthly()
    summary = TimeSeriesAggregator(sample_fraction_model()).process_annual_averages(pre.disaggregate(monthly))
    # The series carries Water_Year, so results are grouped by water year, not calendar year.
    assert summary.index.name == WATER_YEAR_COLUMN
    assert list(summary.index) == [1974, 1975]
    assert summary["Annual_Total_Bedload_m3_yr"].notna().all()


def test_u_m3_01_lognormal_increases_bedload_vs_flat():
    values = {1974: [30.0] * 12}
    model = sample_fraction_model()
    flat_pre, monthly = _monthly(values, sigma=0.0)
    peaky_pre = MonthlyFlowPreprocessor(sigma=0.6)

    flat = model.compute_transport_series(flat_pre.disaggregate(monthly)["Flow Q (m3/s)"].to_numpy()).sum()
    peaky = model.compute_transport_series(peaky_pre.disaggregate(monthly)["Flow Q (m3/s)"].to_numpy()).sum()
    assert peaky > flat


@pytest.mark.parametrize("header", [TURKISH_HEADER, ASCII_HEADER], ids=["turkish", "ascii"])
def test_u_m3_01_is_monthly_flow_table_detects_dsi_headers(header):
    assert is_monthly_flow_table(dsi_table(sample_values(), header=header))


def test_is_monthly_flow_table_routes_malformeddsi_table():
    df = dsi_table(sample_values()).drop(columns=["Şubat"])
    assert is_monthly_flow_table(df)


def test_u_m3_01_prepare_daily_flow_matches_disaggregate_and_reports_conversion():
    df = dsi_table(sample_values(), summary_rows=False)
    pre = MonthlyFlowPreprocessor()

    daily, notes = prepare_daily_flow(df)

    pd.testing.assert_frame_equal(daily, pre.disaggregate(pre.parse_table(df)))
    assert len(notes) == 1
    assert "2 water years" in notes[0]


def test_u_m3_01_is_monthly_flow_table_rejects_daily_series():
    daily = pd.DataFrame({"Date": ["01/01/2000"], "Flow Q (m3/s)": [1.0]})

    assert not is_monthly_flow_table(daily)
    assert not is_monthly_flow_table(daily.rename(columns={"Date": "Tarih", "Flow Q (m3/s)": "Debi"}))


# --- the AR(1) lag-1 component (D62) -----------------------------------------------------------


def _reference_flow(monthly, sigma, phi, seed=0):
    """The AR(1) split written out day by day from the same innovations: the oracle for the vectorised-free loop."""
    flows, z_last, last = [], None, None
    for _, year, month, volume in monthly[[WATER_YEAR_COLUMN, "Year", "Month", "Volume_hm3"]].itertuples(index=False):
        days = pd.Timestamp(year=int(year), month=int(month), day=1).days_in_month
        eps = np.random.default_rng(np.random.SeedSequence([seed, int(year), int(month)])).standard_normal(days)
        follows = last is not None and last + 1 == int(year) * 12 + int(month)
        z = [phi * z_last + np.sqrt(1 - phi**2) * eps[0] if follows else eps[0]]
        for day in range(1, days):
            z.append(phi * z[-1] + np.sqrt(1 - phi**2) * eps[day])
        z_last, last = z[-1], int(year) * 12 + int(month)
        weights = np.exp(sigma * np.array(z) - 0.5 * sigma**2)
        flows.extend(volume * HM3_TO_M3 * weights / weights.sum() / SECONDS_PER_DAY)
    return np.array(flows)


def _lag1_within_months(daily):
    """The mean lag-1 autocorrelation of log flow, taken within each month about the month's mean."""
    log_flow = np.log(daily["Flow Q (m3/s)"])
    deviation = log_flow - log_flow.groupby([daily["Date"].dt.year, daily["Date"].dt.month]).transform("mean")
    same_month = daily["Date"].dt.month.to_numpy()[1:] == daily["Date"].dt.month.to_numpy()[:-1]
    return float(np.corrcoef(deviation.to_numpy()[1:][same_month], deviation.to_numpy()[:-1][same_month])[0, 1])


def test_u_m3_01_phi_defaults_to_zero():
    assert DEFAULT_PHI == 0 and MonthlyFlowPreprocessor().phi == 0


def test_u_m3_01_phi_zero_reproduces_the_independent_lognormal_split():
    pre, monthly = _monthly()
    daily = pre.disaggregate(monthly)

    expected = []
    for _, year, month, volume in monthly[[WATER_YEAR_COLUMN, "Year", "Month", "Volume_hm3"]].itertuples(index=False):
        days = pd.Timestamp(year=int(year), month=int(month), day=1).days_in_month
        rng = np.random.default_rng(np.random.SeedSequence([0, int(year), int(month)]))
        weights = rng.lognormal(mean=-0.5 * pre.sigma**2, sigma=pre.sigma, size=days)
        expected.extend(volume * HM3_TO_M3 * weights / weights.sum() / SECONDS_PER_DAY)
    assert daily["Flow Q (m3/s)"].to_numpy() == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("phi", [0.3, 0.8, 0.95])
def test_u_m3_01_phi_series_matches_the_day_by_day_reference_across_months(phi):
    pre, monthly = _monthly(sigma=0.9, phi=phi, seed=4)

    daily = pre.disaggregate(monthly)

    assert daily["Flow Q (m3/s)"].to_numpy() == pytest.approx(_reference_flow(monthly, 0.9, phi, seed=4), rel=1e-12)


def test_u_m3_01_phi_keeps_every_months_volume_exact():
    pre, monthly = _monthly(phi=0.8)
    daily = pre.disaggregate(monthly)

    got = (daily["Flow Q (m3/s)"] * SECONDS_PER_DAY).groupby(
        [daily["Date"].dt.year, daily["Date"].dt.month]
    ).sum() / HM3_TO_M3
    assert got.to_numpy() == pytest.approx(monthly["Volume_hm3"].to_numpy(), rel=1e-12)


def test_u_m3_01_phi_makes_consecutive_days_alike():
    values = {year: [10.0] * 12 for year in range(1960, 2000)}
    monthly = MonthlyFlowPreprocessor().parse_table(dsi_table(values, summary_rows=False))

    independent = MonthlyFlowPreprocessor(phi=0.0).disaggregate(monthly)
    persistent = MonthlyFlowPreprocessor(phi=0.8).disaggregate(monthly)

    assert abs(_lag1_within_months(independent)) < 0.1
    assert _lag1_within_months(persistent) > 0.5


def test_u_m3_01_the_chain_carries_over_a_month_boundary_and_restarts_after_a_gap():
    values = {1974: [10.0] * 12, 1976: [10.0] * 12}  # water year 1975 is missing
    pre = MonthlyFlowPreprocessor(sigma=1.0, phi=0.9)
    monthly = pre.parse_table(dsi_table(values, summary_rows=False))
    daily = pre.disaggregate(monthly)

    reference = _reference_flow(monthly, 1.0, 0.9)
    assert daily["Flow Q (m3/s)"].to_numpy() == pytest.approx(reference, rel=1e-12)
    restarted = MonthlyFlowPreprocessor(sigma=1.0, phi=0.9).disaggregate(monthly[monthly["Year"] >= 1975])
    first = restarted.iloc[0]["Date"]
    assert daily.loc[daily["Date"] == first, "Flow Q (m3/s)"].iloc[0] == pytest.approx(
        restarted.iloc[0]["Flow Q (m3/s)"], rel=1e-12
    )


@pytest.mark.parametrize("phi", [-0.1, 1.0, 1.5, float("nan"), float("inf")])
def test_u_m3_01_invalid_phi_raises(phi):
    with pytest.raises(ValueError, match="phi"):
        MonthlyFlowPreprocessor(phi=phi)


def test_u_m3_01_prepare_daily_flow_with_phi_is_reported_and_deterministic():
    df = dsi_table(sample_values(), summary_rows=False)

    first, notes = prepare_daily_flow(df, 0.6, 3, 0.8)
    again, _ = prepare_daily_flow(df, 0.6, 3, 0.8)
    flat, flat_notes = prepare_daily_flow(df, 0.6, 3)

    pd.testing.assert_frame_equal(first, again)
    assert "AR(1)" in notes[0] and "φ=0.8" in notes[0] and "AR(1)" not in flat_notes[0]
    assert not np.allclose(first["Flow Q (m3/s)"], flat["Flow Q (m3/s)"])


def test_u_m3_01_a_sigma_above_the_limit_is_an_error_and_the_limit_itself_gives_finite_flow():
    df = dsi_table(sample_values(), summary_rows=False)

    daily, _ = prepare_daily_flow(df, sigma=MAX_SIGMA)

    assert np.isfinite(daily["Flow Q (m3/s)"]).all()
    with pytest.raises(ValueError, match=r"sigma must be a number from 0 to 3 \(got 3\.5\)"):
        prepare_daily_flow(df, sigma=MAX_SIGMA + 0.5)
