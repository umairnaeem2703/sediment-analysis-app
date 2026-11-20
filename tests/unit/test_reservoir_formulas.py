"""U-M4-01 to U-M4-03: the measured reservoir curve of B3.3 (D75, D76) against the hand calculations in
tests/verification/."""

import numpy as np
import pytest

from src.core.reservoir import build_curve, check_h_min, check_table
from tests.oracle import reservoir_cases, reservoir_points, reservoir_tables

CASES = reservoir_cases()
POINTS = reservoir_points()
TABLES = reservoir_tables()

# Case 2 of the oracle: levels 100 to 130 m, Hmin 110 m
LEVELS, VOLUMES, AREAS = [100.0, 110.0, 120.0, 130.0], [0.0, 10.0, 30.0, 60.0], [0.5, 1.5, 2.5, 3.5]


def _case(number):
    return next(case for case in CASES if case["Case"] == number)


def _curve(number=2, h_min_m=None):
    rows = [row for row in TABLES if row["Case"] == number]
    columns = ([row[name] for row in rows] for name in ("Elevation_m", "Volume_hm3", "Area_km2"))
    return build_curve(*columns, h_min_m=_case(number)["Hmin_m"] if h_min_m is None else h_min_m)


# --- U-M4-01: the table and Hmin -------------------------------------------------------------


def test_u_m4_01_a_rising_table_has_no_problems():
    assert check_table(LEVELS, VOLUMES, AREAS) == []


@pytest.mark.parametrize(
    ("levels", "volumes", "areas", "expected"),
    [
        ([100.0, 110.0, 110.0, 130.0], VOLUMES, AREAS, "row 4: the level 110 m"),
        ([100.0, 120.0, 110.0, 130.0], VOLUMES, AREAS, "row 4: the level 110 m"),
        (LEVELS, [0.0, 10.0, 10.0, 60.0], AREAS, "row 4: the volume 10 hm³"),
        (LEVELS, [-1.0, 10.0, 30.0, 60.0], AREAS, "row 2: the volume and the surface area"),
        (LEVELS, VOLUMES, [0.5, -1.5, 2.5, 3.5], "row 3: the volume and the surface area"),
    ],
)
def test_u_m4_01_each_problem_of_the_table_is_named_with_its_row(levels, volumes, areas, expected):
    problems = check_table(levels, volumes, areas)

    assert len(problems) == 1 and problems[0].startswith(expected)


def test_u_m4_01_a_table_needs_two_rows():
    assert check_table([100.0], [0.0], [0.0]) == ["The curve needs at least two rows, found 1."]


def test_u_m4_01_the_rows_of_the_messages_can_be_given():
    problems = check_table(LEVELS, [0.0, 10.0, 10.0, 60.0], AREAS, rows=[2, 3, 5, 6])

    assert problems[0].startswith("row 5:")


def test_u_m4_01_an_hmin_inside_the_curve_has_no_problems():
    assert check_h_min(LEVELS, 110.0) == [] and check_h_min(LEVELS, 100.01) == []


@pytest.mark.parametrize("h_min", [100.0, 130.0, 95.0, 131.0])
def test_u_m4_01_an_hmin_at_or_outside_the_ends_of_the_curve_is_refused(h_min):
    problems = check_h_min(LEVELS, h_min)

    assert problems == [f"Hmin ({h_min:g} m) must lie above Hbed (100 m) and below Hcrest (130 m) of the curve."]


def test_u_m4_01_hmin_must_be_finite():
    assert check_h_min(LEVELS, float("nan")) == ["Hmin must be a finite number, found nan."]


def test_u_m4_01_a_curve_is_not_built_from_a_bad_table_or_an_hmin_outside_it():
    with pytest.raises(ValueError, match="cannot be used:\n- row 4: the volume"):
        build_curve(LEVELS, [0.0, 10.0, 10.0, 60.0], AREAS, h_min_m=110.0)
    with pytest.raises(ValueError, match=r"Hmin \(140 m\)"):
        build_curve(LEVELS, VOLUMES, AREAS, h_min_m=140.0)


# --- U-M4-02: the curve -----------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"case{int(case['Case'])}")
def test_u_m4_02_the_curve_matches_the_hand_calculation(case):
    curve = _curve(int(case["Case"]))

    assert curve.h_min_m == case["Hmin_m"]
    assert (curve.bed_elev_m, curve.crest_elev_m, curve.max_vol_hm3) == (
        case["Hbed_m"],
        case["Hcrest_m"],
        case["Vmax_hm3"],
    )
    assert curve.dead_vol_hm3 == pytest.approx(case["Vdead_hm3"], rel=1e-12)


@pytest.mark.parametrize("point", POINTS, ids=lambda point: f"case{int(point['Case'])}-{point['Point']}")
def test_u_m4_02_volume_area_and_the_inverse_match_the_hand_calculation(point):
    curve = _curve(int(point["Case"]))

    assert curve.volume(point["H_m"]) == pytest.approx(point["V_hm3"], rel=1e-12, abs=1e-12)
    assert curve.area(point["H_m"]) == pytest.approx(point["A_km2"], rel=1e-12, abs=1e-12)
    assert curve.elevation(point["V_hm3"]) == pytest.approx(point["H_m"], rel=1e-12)


def test_u_m4_02_vdead_is_the_volume_at_hmin_and_the_ends_come_from_the_curve():
    curve = _curve()

    assert curve.h_min_m == 110.0 and curve.elevation(curve.dead_vol_hm3) == 110.0 and curve.dead_vol_hm3 == 10.0
    assert (curve.bed_elev_m, curve.crest_elev_m, curve.max_vol_hm3) == (100.0, 130.0, 60.0)


def test_u_m4_02_the_curve_is_held_at_its_first_and_last_rows():
    curve = _curve()

    assert curve.volume(90.0) == 0.0 and curve.volume(140.0) == 60.0
    assert curve.elevation(-5.0) == 100.0 and curve.elevation(70.0) == 130.0


def test_u_m4_02_the_curve_takes_arrays_and_numbers():
    curve = _curve()

    assert isinstance(curve.volume(105.0), float) and isinstance(curve.elevation(5.0), float)
    assert list(curve.volume(np.array([100.0, 125.0]))) == [0.0, 45.0]
    assert list(curve.elevation(np.array([20.0]))) == [115.0]


# --- U-M4-03: the table -----------------------------------------------------------------------


@pytest.mark.parametrize("number", [1, 2])
def test_u_m4_03_the_table_is_the_rows_of_the_curve_sheet(number):
    rows = [row for row in TABLES if row["Case"] == number]

    table = _curve(number).table()

    assert list(table.columns) == ["Elevation_m", "Volume_hm3", "Area_km2"]
    assert table.to_dict("records") == [{key: row[key] for key in table.columns} for row in rows]
