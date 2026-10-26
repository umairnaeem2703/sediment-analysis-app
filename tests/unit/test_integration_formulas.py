"""U-M4-04 to U-M4-07: annual totals, accumulation to date, projection and lifespan of B3.4 against the hand
calculations in tests/verification/."""

import numpy as np
import pandas as pd
import pytest

from src.core.integration import annual_totals, retained_hm3, sediment_elevations
from src.core.projection import (
    EXCEEDED,
    HORIZON_YEARS,
    NOT_REACHED,
    YEAR,
    accumulate,
    annual_rates,
    exceeded_year,
    lifespan,
    project,
)
from src.core.reservoir import ReservoirCurve, fit_curve
from tests.oracle import integration_accumulation, integration_cases, integration_projection, integration_record

CASES = integration_cases()
RECORD = integration_record()
ACCUMULATION = integration_accumulation()
PROJECTION = integration_projection()
NUMBERS = [int(case["Case"]) for case in CASES]
RATES = ("Mean", "Min", "Max")


def _case(number):
    return next(case for case in CASES if int(case["Case"]) == number)


def _curve(number) -> ReservoirCurve:
    case = _case(number)
    curve = fit_curve(
        bed_elev_m=case["Hbed_m"],
        max_elev_m=case["Hmax_m"],
        crest_elev_m=case["Hcrest_m"],
        active_vol_hm3=case["Vactive_hm3"],
        max_vol_hm3=case["Vmax_hm3"],
        shape_class="hill",
    )
    assert curve.exponent == case["m"]
    return curve


def _record(number):
    return [row for row in RECORD if int(row["Case"]) == number]


def _totals(number):
    case, rows = _case(number), _record(number)
    return annual_totals([row["Bedload_m3_yr"] for row in rows], case["Suspended_m3_yr"], case["TE_pct"])


def _accumulate(number):
    case = _case(number)
    years = [int(row["Year"]) for row in _record(number)]
    return accumulate(years, _totals(number), int(case["Commissioning_year"]), int(case["Analysis_year"]))


def _expected(text_or_number):
    return text_or_number if isinstance(text_or_number, str) else pytest.approx(text_or_number, rel=1e-12)


# --- U-M4-04: annual totals and elevations ----------------------------------------------------


@pytest.mark.parametrize("number", NUMBERS)
def test_u_m4_04_the_annual_total_is_te_times_suspended_plus_bedload_in_hm3(number):
    expected = [row["Total_hm3"] for row in _record(number)]

    assert list(_totals(number)) == pytest.approx(expected, rel=1e-12, abs=1e-15)


@pytest.mark.parametrize("number", NUMBERS)
def test_u_m4_04_the_elevation_of_each_year_is_read_from_the_curve(number):
    elevations, clamped = sediment_elevations(_curve(number), _totals(number))

    assert list(elevations) == pytest.approx([row["Elevation_m"] for row in _record(number)], rel=1e-12)
    assert clamped == 0


def test_u_m4_04_the_units_are_hm3_and_the_trap_efficiency_is_a_percentage():
    assert list(annual_totals([1_000_000.0, 3_000_000.0], 1_000_000.0, 100.0)) == [2.0, 4.0]
    assert list(annual_totals([1_000_000.0, 3_000_000.0], 1_000_000.0, 50.0)) == [1.0, 2.0]


def test_u_m4_04_the_retained_part_is_te_times_the_volume_in_hm3():
    assert list(retained_hm3([1_000_000.0, 3_000_000.0], 50.0)) == [0.5, 1.5]
    assert list(retained_hm3([2_000_000.0], 100.0)) == [2.0]


def test_u_m4_04_a_volume_above_the_crest_is_limited_to_hcrest_and_counted():
    curve = _curve(1)  # V(Hcrest) = 242 hm3

    elevations, clamped = sediment_elevations(curve, [0.0, 100.0, 241.9, 242.5, 1e6])

    assert list(elevations[[0, 3, 4]]) == [100.0, 155.0, 155.0] and elevations[2] < 155.0
    assert clamped == 2


def test_u_m4_04_exactly_the_volume_at_the_crest_is_not_limited():
    curve = _curve(1)

    elevations, clamped = sediment_elevations(curve, [curve.volume(curve.crest_elev_m)])

    assert elevations[0] == pytest.approx(155.0, rel=1e-12) and clamped == 0


def test_u_m4_04_no_sediment_reaches_the_bed():
    assert list(sediment_elevations(_curve(1), np.array([0.0]))[0]) == [100.0]


# --- U-M4-05: accumulation to date ------------------------------------------------------------


@pytest.mark.parametrize("number", NUMBERS)
def test_u_m4_05_the_accumulation_matches_the_hand_calculation_year_by_year(number):
    expected = [row for row in ACCUMULATION if int(row["Case"]) == number]

    result = _accumulate(number)

    assert list(result.table.columns) == ["Year", "In_Record", "Total_Used_hm3", "Cumulative_hm3"]
    assert list(result.table["Year"]) == [int(row["Year"]) for row in expected]
    assert list(result.table["In_Record"]) == [int(row["In_Record"]) for row in expected]
    assert list(result.table["Total_Used_hm3"]) == pytest.approx([row["Total_Used_hm3"] for row in expected], rel=1e-12)
    assert list(result.table["Cumulative_hm3"]) == pytest.approx([row["Cumulative_hm3"] for row in expected], rel=1e-12)
    assert result.volume_hm3 == pytest.approx(_case(number)["S0_hm3"], rel=1e-12, abs=1e-15)


def test_u_m4_05_years_outside_the_record_use_the_mean_and_years_before_commissioning_are_ignored():
    outside = _accumulate(2).table  # commissioned in 1999, analysed in 2008, record 2001 to 2005
    ignored = _accumulate(3).table  # commissioned in 2003: the record years 2001 and 2002 are left out

    assert list(outside.loc[outside["In_Record"] == 0, "Year"]) == [1999, 2000, 2006, 2007]
    assert set(outside.loc[outside["In_Record"] == 0, "Total_Used_hm3"].round(12)) == {3.3}
    assert list(ignored["Year"]) == [2003, 2004, 2005]


def test_u_m4_05_the_accumulated_volume_is_the_last_cumulative_value_to_the_last_digit():
    # sum() of ten 0.1 is 1.0 but their running total ends at 0.9999999999999999: the two must not be mixed
    result = accumulate(range(2000, 2010), [0.1] * 10, 2000, 2010)

    assert result.volume_hm3 == result.table["Cumulative_hm3"].iloc[-1]
    assert exceeded_year(result.table, result.volume_hm3) == 2009
    assert lifespan(result.volume_hm3, result.volume_hm3, 1.0, 2010).status == EXCEEDED


def test_u_m4_05_the_analysis_year_itself_is_not_accumulated():
    table = _accumulate(1).table  # analysed in 2006

    assert table["Year"].max() == 2005


def test_u_m4_05_the_mean_for_missing_years_is_over_the_whole_record():
    # commissioned in 2004: the record's 2001 to 2003 are ignored, but they still count in the mean (5.5)
    result = accumulate([2001, 2002, 2003, 2004, 2005], [5.0, 6.5, 4.5, 6.0, 5.5], 2004, 2008)

    assert result.volume_hm3 == pytest.approx(6.0 + 5.5 + 5.5 + 5.5)


def test_u_m4_05_analysing_in_the_commissioning_year_gives_an_empty_accumulation():
    result = _accumulate(4)

    assert result.table.empty and result.volume_hm3 == 0.0


def test_u_m4_05_an_analysis_year_before_commissioning_is_an_error():
    with pytest.raises(ValueError, match="before the commissioning year"):
        accumulate([2001, 2002], [1.0, 2.0], 2005, 2004)


# --- U-M4-06: projection ----------------------------------------------------------------------


@pytest.mark.parametrize("number", NUMBERS)
def test_u_m4_06_the_rates_are_the_mean_min_and_max_of_the_record(number):
    rates = annual_rates(_totals(number))

    assert list(rates) == list(RATES)
    for name in RATES:
        assert rates[name] == pytest.approx(_case(number)[f"Rate_{name}_hm3_yr"], rel=1e-12, abs=1e-15)


@pytest.mark.parametrize("number", NUMBERS)
def test_u_m4_06_the_projection_matches_the_hand_calculation(number):
    case = _case(number)
    rates, s0, analysis = annual_rates(_totals(number)), case["S0_hm3"], int(case["Analysis_year"])

    for row in (row for row in PROJECTION if int(row["Case"]) == number):
        table = project(s0, rates[row["Rate"]], analysis)
        at = table.loc[table["Year"] == int(row["Year"])]
        assert len(at) == 1
        assert float(at["Cumulative_hm3"].iloc[0]) == pytest.approx(row["Cumulative_hm3"], rel=1e-12, abs=1e-15)


@pytest.mark.parametrize("number", NUMBERS)
def test_u_m4_06_the_elevation_of_the_projection_is_read_from_the_curve_and_limited_to_the_crest(number):
    case, curve = _case(number), _curve(number)
    rates = annual_rates(_totals(number))

    for row in (row for row in PROJECTION if int(row["Case"]) == number):
        volume = project(case["S0_hm3"], rates[row["Rate"]], int(case["Analysis_year"]))
        elevation = sediment_elevations(curve, volume["Cumulative_hm3"])[0][volume["Year"] == int(row["Year"])]
        assert float(elevation[0]) == pytest.approx(row["Elevation_m"], rel=1e-12)


def test_u_m4_06_the_projection_runs_100_years_from_the_analysis_year_in_a_straight_line():
    table = project(10.0, 2.5, 2020)

    assert list(table.columns) == ["Year", "Cumulative_hm3"]
    assert len(table) == HORIZON_YEARS + 1 == 101
    assert table["Year"].iloc[0] == 2020 and table["Year"].iloc[-1] == 2120
    assert table["Cumulative_hm3"].iloc[0] == 10.0 and table["Cumulative_hm3"].iloc[-1] == 260.0
    assert np.allclose(np.diff(table["Cumulative_hm3"]), 2.5)


def test_u_m4_06_no_sediment_gives_a_flat_projection():
    assert set(project(3.0, 0.0, 2020)["Cumulative_hm3"]) == {3.0}


# --- U-M4-07: lifespan ------------------------------------------------------------------------


@pytest.mark.parametrize("name", RATES)
@pytest.mark.parametrize("number", NUMBERS)
def test_u_m4_07_the_lifespan_matches_the_hand_calculation(number, name):
    case = _case(number)

    result = lifespan(case["Vdead_hm3"], case["S0_hm3"], case[f"Rate_{name}_hm3_yr"], int(case["Analysis_year"]))

    expected = case[f"Lifespan_{name}"]
    if isinstance(expected, str):
        assert result.status == expected and result.year is None
    else:
        assert result.status == YEAR and result.year == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("number", NUMBERS)
def test_u_m4_07_the_year_the_dead_volume_was_passed_matches_the_hand_calculation(number):
    expected = _case(number)["Exceeded_Year"]

    found = exceeded_year(_accumulate(number).table, _case(number)["Vdead_hm3"])

    assert found == (None if expected == "" else int(expected))


def test_u_m4_07_the_dead_volume_is_passed_in_the_first_year_the_cumulative_volume_reaches_it():
    table = pd.DataFrame({"Year": [2001, 2002, 2003], "Cumulative_hm3": [30.0, 80.0, 90.0]})

    assert exceeded_year(table, 80.0) == 2002  # reaching it exactly counts
    assert exceeded_year(table, 90.1) is None
    assert exceeded_year(table.iloc[0:0], 1.0) is None


def test_u_m4_07_exactly_the_dead_volume_is_already_exceeded():
    assert lifespan(80.0, 80.0, 5.0, 2020).status == EXCEEDED


def test_u_m4_07_a_zero_rate_never_fills_the_reservoir_but_a_full_one_is_exceeded_even_then():
    assert lifespan(80.0, 10.0, 0.0, 2020).status == NOT_REACHED
    assert lifespan(80.0, 90.0, 0.0, 2020).status == EXCEEDED


def test_u_m4_07_the_lifespan_is_the_analysis_year_plus_the_years_to_fill_the_rest():
    assert lifespan(80.0, 30.0, 5.0, 2020).year == 2030.0
