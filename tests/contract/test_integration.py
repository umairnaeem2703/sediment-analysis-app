"""C-M4-02: the integration service (FR-M4-03 to FR-M4-05, B3.4): its inputs, its tables and its warnings."""

import datetime

import pandas as pd
import pytest

from src.core.projection import EXCEEDED, NOT_REACHED, YEAR
from src.core.reservoir import curve_table, fit_curve
from src.services.bedload import VALUE_COLUMNS, VOLUME_M3, BedloadResult
from src.services.integration import (
    INTEGRATION_CSV,
    PROJECTION_CSV,
    compute_dam_integration,
    compute_integration,
    parse_horizon,
    write_integration_csv,
    write_projection_csv,
)
from src.services.project import Dam
from src.services.reservoir import CurveResult
from src.services.suspended import TOTAL_COLUMNS, SuspendedResult
from tests.oracle import integration_cases, integration_projection, integration_record

CASES = integration_cases()
NUMBERS = [int(case["Case"]) for case in CASES]
RATES = ("Mean", "Min", "Max")


def _case(number):
    return next(case for case in CASES if int(case["Case"]) == number)


def _curve(number=1):
    case = _case(number)
    return fit_curve(
        bed_elev_m=case["Hbed_m"],
        max_elev_m=case["Hmax_m"],
        crest_elev_m=case["Hcrest_m"],
        active_vol_hm3=case["Vactive_hm3"],
        max_vol_hm3=case["Vmax_hm3"],
        shape_class="hill",
    )


def _bedload(volumes_m3, years=(2001, 2002, 2003, 2004, 2005), year_column="Water_Year") -> BedloadResult:
    table = pd.DataFrame({year_column: list(years)})
    for column in VALUE_COLUMNS:
        table[column] = 0.0
    table[VOLUME_M3] = list(volumes_m3)
    return BedloadResult(table, True, [], [])


def _bedload_of(number) -> BedloadResult:
    return _bedload([row["Bedload_m3_yr"] for row in integration_record() if int(row["Case"]) == number])


def _run(number, **changes):
    case = _case(number)
    values = {
        "trap_efficiency_pct": case["TE_pct"],
        "commissioning_year": int(case["Commissioning_year"]),
        "analysis_year": int(case["Analysis_year"]),
    }
    return compute_integration(case["Suspended_m3_yr"], _bedload_of(number), _curve(number), **{**values, **changes})


# --- the numbers ------------------------------------------------------------------------------


@pytest.mark.parametrize("number", NUMBERS)
def test_c_m4_02_the_service_reproduces_the_hand_calculation(number):
    case, result = _case(number), _run(number)

    assert result.accumulated_hm3 == pytest.approx(case["S0_hm3"], rel=1e-12, abs=1e-15)
    assert result.accumulated_elevation_m == pytest.approx(case["S0_Elevation_m"], rel=1e-12)
    assert result.dead_vol_hm3 == pytest.approx(case["Vdead_hm3"], rel=1e-12)
    assert result.h_min_m == pytest.approx(case["Hmin_m"], rel=1e-12)
    for name in RATES:
        assert result.rates[name] == pytest.approx(case[f"Rate_{name}_hm3_yr"], rel=1e-12, abs=1e-15)
        expected = case[f"Lifespan_{name}"]
        lifespan = result.lifespans[name]
        if isinstance(expected, str):
            assert lifespan.status == expected and lifespan.year is None
        else:
            assert lifespan.status == YEAR and lifespan.year == pytest.approx(expected, rel=1e-12)
    expected_year = case["Exceeded_Year"]
    assert result.exceeded_year == (None if expected_year == "" else int(expected_year))


@pytest.mark.parametrize("number", NUMBERS)
def test_c_m4_02_the_annual_table_matches_the_hand_calculation(number):
    result = _run(number)
    rows = [row for row in integration_record() if int(row["Case"]) == number]

    assert list(result.annual.columns) == ["Water_Year", "Suspended_hm3", "Bedload_hm3", "Total_hm3", "Elevation_m"]
    assert list(result.annual["Water_Year"]) == [int(row["Year"]) for row in rows]
    assert list(result.annual["Total_hm3"]) == pytest.approx([row["Total_hm3"] for row in rows], rel=1e-12, abs=1e-15)
    assert list(result.annual["Elevation_m"]) == pytest.approx([row["Elevation_m"] for row in rows], rel=1e-12)


def test_c_m4_02_the_annual_columns_are_what_stays_in_the_reservoir():
    result = _run(2)  # TE 60 percent
    case = _case(2)

    assert list(result.annual["Suspended_hm3"]) == pytest.approx([0.6 * case["Suspended_m3_yr"] / 1e6] * 5)
    assert list(result.annual["Suspended_hm3"] + result.annual["Bedload_hm3"]) == pytest.approx(
        list(result.annual["Total_hm3"]), rel=1e-12
    )


@pytest.mark.parametrize("number", NUMBERS)
def test_c_m4_02_the_projection_matches_the_hand_calculation(number):
    result = _run(number)

    assert list(result.projection.columns) == ["Year"] + [f"Cumulative_{name}_hm3" for name in RATES] + [
        f"Elevation_{name}_m" for name in RATES
    ]
    assert len(result.projection) == 101
    for row in (row for row in integration_projection() if int(row["Case"]) == number):
        at = result.projection.loc[result.projection["Year"] == int(row["Year"])].iloc[0]
        assert at[f"Cumulative_{row['Rate']}_hm3"] == pytest.approx(row["Cumulative_hm3"], rel=1e-12, abs=1e-15)
        assert at[f"Elevation_{row['Rate']}_m"] == pytest.approx(row["Elevation_m"], rel=1e-12)


@pytest.mark.parametrize(("text", "years"), [("100", 100), (" 30 ", 30), ("30.0", 30), ("1", 1)])
def test_c_m4_02_the_number_of_years_is_read_as_a_whole_number(text, years):
    assert parse_horizon(text) == years and isinstance(parse_horizon(text), int)


@pytest.mark.parametrize("text", ["", "x", "nan", "0", "-10", "2,5", "12.5"])
def test_c_m4_02_a_number_of_years_that_is_blank_not_a_number_or_not_whole_is_refused(text):
    with pytest.raises(ValueError, match="projection years"):
        parse_horizon(text)


def test_c_m4_02_the_projection_runs_the_entered_number_of_years_and_nothing_else_changes():
    default, short = _run(1), _run(1, horizon_years=30)

    assert len(short.projection) == 31 and short.projection["Year"].iloc[-1] == int(_case(1)["Analysis_year"]) + 30
    pd.testing.assert_frame_equal(short.projection, default.projection.iloc[:31])
    assert short.lifespans == default.lifespans and short.accumulated_hm3 == default.accumulated_hm3
    assert len(_run(1, horizon_years=150).projection) == 151


def test_c_m4_02_an_invalid_number_of_years_is_refused():
    with pytest.raises(ValueError, match="projection years"):
        _run(1, horizon_years=0)


def test_c_m4_02_the_year_labels_are_used_as_they_are():
    water = _run(1)
    calendar = compute_integration(
        4_000_000.0,
        _bedload([1e6, 2e6, 1e6], years=(2001, 2002, 2003), year_column="Year"),
        _curve(),
        trap_efficiency_pct=100.0,
        commissioning_year=2001,
        analysis_year=2004,
    )

    assert water.year_column == "Water_Year" and calendar.year_column == "Year"
    assert list(calendar.annual["Year"]) == [2001, 2002, 2003]


# --- the inputs -------------------------------------------------------------------------------


def test_c_m4_02_a_missing_commissioning_year_is_an_error_that_says_where_to_enter_it():
    with pytest.raises(ValueError, match=r"commissioning year.*step 3"):
        _run(1, commissioning_year=None)


def test_c_m4_02_an_analysis_year_before_the_commissioning_year_is_an_error():
    with pytest.raises(ValueError, match=r"2000.*before.*2005"):
        _run(1, commissioning_year=2005, analysis_year=2000)


def test_c_m4_02_an_empty_bedload_record_is_an_error():
    with pytest.raises(ValueError, match="no bedload"):
        compute_integration(
            1e6,
            _bedload([], years=()),
            _curve(),
            trap_efficiency_pct=100.0,
            commissioning_year=2001,
            analysis_year=2004,
        )


def _dam(**changes) -> Dam:
    values = {"commissioning_year": 2001, "analysis_year": 2006, "trap_efficiency_pct": 100.0}
    return Dam(name="Test", slug="test", **{**values, **changes})


def _suspended(volume_m3) -> SuspendedResult:
    row = dict.fromkeys(TOTAL_COLUMNS, 0.0)
    row["Volume_m3"] = volume_m3
    return SuspendedResult(pd.DataFrame([row]), [])


def _curve_result(number=1) -> CurveResult:
    curve = _curve(number)
    return CurveResult(curve, curve_table(curve), False, "hill", [])


def test_c_m4_02_a_dam_takes_its_own_settings_and_the_suspended_total():
    case = _case(2)
    dam = _dam(trap_efficiency_pct=60.0, commissioning_year=1999, analysis_year=2008)

    result = compute_dam_integration(_suspended(case["Suspended_m3_yr"]), _bedload_of(2), _curve_result(), dam)

    assert (result.commissioning_year, result.analysis_year, result.trap_efficiency_pct) == (1999, 2008, 60.0)
    assert result.accumulated_hm3 == pytest.approx(case["S0_hm3"], rel=1e-12)


def test_c_m4_02_a_blank_analysis_year_is_the_current_year_and_is_recorded():
    dam = _dam(analysis_year=None)

    explicit = compute_dam_integration(_suspended(4e6), _bedload_of(1), _curve_result(), dam, this_year=2010)
    default = compute_dam_integration(_suspended(4e6), _bedload_of(1), _curve_result(), dam)

    assert explicit.analysis_year == 2010
    assert default.analysis_year == datetime.date.today().year


# --- the warnings -----------------------------------------------------------------------------


def test_c_m4_02_years_outside_the_record_are_reported():
    warnings = _run(2).warnings  # 1999, 2000, 2006 and 2007

    assert any("4 year(s)" in warning and "not in the record" in warning for warning in warnings)


def test_c_m4_02_no_warning_when_the_record_covers_the_years_and_nothing_reaches_the_crest():
    assert _run(7).warnings == []


def test_c_m4_02_a_projection_above_the_crest_volume_is_limited_and_reported():
    result = _run(1)  # 27.5 + 100 x 5.5 = 577 hm3, above V(Hcrest) = 242 hm3

    warnings = [warning for warning in result.warnings if "projected" in warning]
    assert len(warnings) == 1 and "crest" in warnings[0]
    assert result.projection["Elevation_Mean_m"].max() == 155.0


def test_c_m4_02_an_accumulation_or_a_year_above_the_crest_volume_is_limited_and_reported():
    result = compute_integration(
        300e6,
        _bedload([0.0] * 5),
        _curve(),
        trap_efficiency_pct=100.0,
        commissioning_year=2001,
        analysis_year=2003,
    )  # every year delivers 300 hm3 and the crest volume is 242 hm3

    assert any("year(s) of the record" in warning for warning in result.warnings)
    assert any("accumulation to date" in warning for warning in result.warnings)
    assert result.accumulated_elevation_m == 155.0 and list(result.annual["Elevation_m"]) == [155.0] * 5


# --- the files --------------------------------------------------------------------------------


def test_c_m4_02_the_tables_are_written_as_utf8_with_bom(tmp_path):
    result = _run(1)

    annual, projection = write_integration_csv(result, tmp_path), write_projection_csv(result, tmp_path)

    assert annual.name == INTEGRATION_CSV == "integration.csv"
    assert projection.name == PROJECTION_CSV == "projection.csv"
    for path in (annual, projection):
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    pd.testing.assert_frame_equal(
        pd.read_csv(annual, encoding="utf-8-sig"), result.annual, check_exact=False, rtol=1e-12
    )
    pd.testing.assert_frame_equal(
        pd.read_csv(projection, encoding="utf-8-sig"), result.projection, check_exact=False, rtol=1e-12
    )


def test_c_m4_02_the_lifespan_states_are_the_documented_ones():
    assert (YEAR, EXCEEDED, NOT_REACHED) == ("year", "exceeded", "not reached")
