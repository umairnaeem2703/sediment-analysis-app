"""D74: how an annual bedload record is spread over its years, against figures worked out by hand."""

import pandas as pd
import pytest

from src.core.record import TOP_YEARS, record_stats
from src.services.bedload import FLOW_M3_S, MASS_T, VOLUME_M3, QB_M2_S, BedloadResult
from src.core.wilcock import WATER_YEAR_COLUMN

YEARS = [2000, 2001, 2002, 2003, 2004, 2005]
FLOW = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
LOAD = [0.5, 100.0, 200.0, 300.0, 1000.0, 8400.0]  # total 10,000.5, mean 1,666.75


def test_d74_the_share_of_the_largest_years_the_median_and_the_mean_without_the_largest_year():
    stats = record_stats(pd.Series(YEARS), pd.Series(FLOW), pd.Series(LOAD))
    assert stats.top_years == [2005, 2004, 2003]
    assert stats.top_share == pytest.approx(9700 / 10000.5)
    assert stats.mean == pytest.approx(10000.5 / 6)
    assert stats.median == pytest.approx(250.0)
    assert stats.largest_year == 2005
    assert stats.mean_without_largest == pytest.approx(1600.5 / 5)
    assert stats.negligible_years == [2000]  # below 1% of the mean, 16.67
    assert stats.rank_correlation == pytest.approx(1.0)


def test_d74_a_reversed_order_gives_a_negative_rank_correlation_and_a_constant_flow_none():
    stats = record_stats(pd.Series(YEARS), pd.Series(FLOW[::-1]), pd.Series(LOAD))
    assert stats.rank_correlation == pytest.approx(-1.0)
    flat = record_stats(pd.Series(YEARS), pd.Series([1.0] * 6), pd.Series(LOAD))
    assert flat.rank_correlation is None  # a constant flow has no order


@pytest.mark.parametrize("load", [LOAD[:TOP_YEARS], [0.0] * 6])
def test_d74_a_short_record_or_one_without_load_has_no_statistics(load):
    n = len(load)
    assert record_stats(pd.Series(YEARS[:n]), pd.Series(FLOW[:n]), pd.Series(load)) is None


def _result(flow, load) -> BedloadResult:
    table = pd.DataFrame({WATER_YEAR_COLUMN: YEARS, FLOW_M3_S: flow, QB_M2_S: 0.0, VOLUME_M3: 0.0, MASS_T: load})
    return BedloadResult(table, False, [], [])


def test_d74_the_result_states_the_spread_and_flags_a_concentrated_load():
    lines = _result(FLOW, LOAD).record_lines
    assert lines == [
        "⚠ The 3 largest years (2005, 2004, 2003) carry 97% of the bedload.",
        "Median year 250 t/yr against a mean of 1,667 t/yr; without 2005 the mean is 320 t/yr (-81%).",
        "1 of 6 years carry under 1% of the mean: 2000.",
        "Rank correlation of the bedload with the annual mean flow: 1.00.",
    ]


def test_d74_a_load_that_does_not_follow_the_flow_is_flagged():
    lines = _result(FLOW[::-1], [1000.0, 900.0, 1100.0, 950.0, 1050.0, 1000.0]).record_lines
    assert lines[-1].startswith("⚠ The bedload follows the order of the annual mean flow poorly")
