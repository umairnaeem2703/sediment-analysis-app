"""U-M4-01 to U-M4-03: the measured reservoir curve of B3.3 (D75) against the hand calculations in tests/verification/."""

import numpy as np
import pytest

from src.core.reservoir import (
    LEVEL_TOLERANCE_M,
    VOLUME_TOLERANCE,
    build_curve,
    check_agreement,
    check_table,
    curve_warnings,
)
from tests.oracle import reservoir_cases, reservoir_points, reservoir_tables

CASES = reservoir_cases()
POINTS = reservoir_points()
TABLES = reservoir_tables()

# Case 2 of the oracle: levels 100 to 130 m, Vmax 45 hm3 at Hmax 125 m
LEVELS, VOLUMES, AREAS = [100.0, 110.0, 120.0, 130.0], [0.0, 10.0, 30.0, 60.0], [0.5, 1.5, 2.5, 3.5]


def _case(number):
    return next(case for case in CASES if case["Case"] == number)


def _sheet(number=2, **changes):
    case = _case(number)
    values = {
        "bed_elev_m": case["Hbed_m"],
        "max_elev_m": case["Hmax_m"],
        "crest_elev_m": case["Hcrest_m"],
        "active_vol_hm3": case["Vactive_hm3"],
        "max_vol_hm3": case["Vmax_hm3"],
    }
    return {**values, **changes}


def _curve(number=2, **changes):
    rows = [row for row in TABLES if row["Case"] == number]
    columns = ([row[name] for row in rows] for name in ("Elevation_m", "Volume_hm3", "Area_km2"))
    return build_curve(*columns, **_sheet(number, **changes))


# --- U-M4-01: the table and its agreement with the dam sheet ----------------------------------


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


def test_u_m4_01_a_dam_sheet_that_agrees_has_no_problems():
    assert check_agreement(LEVELS, VOLUMES, **_sheet()) == []


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"bed_elev_m": 99.4}, "Hbed on the dam sheet (99.4 m) differs from the first level of the curve (100 m)"),
        ({"crest_elev_m": 130.6}, "Hcrest on the dam sheet (130.6 m) differs from the last level of the curve (130 m)"),
        (
            {"max_vol_hm3": 45.5},
            "Vmax on the dam sheet (45.5 hm³) differs from the curve's volume at Hmax = 125 m (45 hm³)",
        ),
        ({"max_vol_hm3": 44.5}, "Vmax on the dam sheet (44.5 hm³)"),
        ({"active_vol_hm3": 0.0}, "Vactive"),
        ({"active_vol_hm3": 45.0}, "Vactive"),
        ({"max_elev_m": 100.0}, "Hbed (100 m) < Hmax (100 m)"),
        ({"bed_elev_m": float("nan")}, "Hbed must be a finite number"),
    ],
)
def test_u_m4_01_each_disagreement_is_named_with_both_values(changes, expected):
    problems = check_agreement(LEVELS, VOLUMES, **_sheet(**changes))

    assert any(expected in problem for problem in problems), problems


def test_u_m4_01_the_tolerances_are_half_a_metre_and_one_percent():
    assert (LEVEL_TOLERANCE_M, VOLUME_TOLERANCE) == (0.5, 0.01)
    within = _sheet(bed_elev_m=99.5, crest_elev_m=130.5, max_vol_hm3=45.0 * 1.0099)

    assert check_agreement(LEVELS, VOLUMES, **within) == []


def test_u_m4_01_hmax_outside_the_curve_is_refused():
    problems = check_agreement([100.0, 110.0, 120.0], [0.0, 10.0, 30.0], **_sheet(crest_elev_m=125.0))

    assert any("Hmax on the dam sheet (125 m) is outside the curve (100 m to 120 m)" in p for p in problems)


def test_u_m4_01_every_disagreement_is_listed_at_once():
    problems = check_agreement(LEVELS, VOLUMES, **_sheet(bed_elev_m=95.0, max_vol_hm3=50.0))

    assert len(problems) == 2


def test_u_m4_01_a_curve_is_not_built_from_a_bad_table_or_a_disagreeing_sheet():
    with pytest.raises(ValueError, match="cannot be used:\n- row 4: the volume"):
        build_curve(LEVELS, [0.0, 10.0, 10.0, 60.0], AREAS, **_sheet())
    with pytest.raises(ValueError, match="Hbed on the dam sheet"):
        build_curve(LEVELS, VOLUMES, AREAS, **_sheet(bed_elev_m=90.0))


def test_u_m4_01_the_kavsakkaya_dam_sheet_disagrees_with_its_curve_sheet():
    """OI-11: the sample dam sheet of Kavşakkaya, refused against the hydrologist's curve."""
    problems = check_agreement(
        [row["Elevation_m"] for row in TABLES if row["Case"] == 1],
        [row["Volume_hm3"] for row in TABLES if row["Case"] == 1],
        **_sheet(1, bed_elev_m=1063.0, max_vol_hm3=80.8),
    )

    assert len(problems) == 2
    assert "Hbed on the dam sheet (1063 m)" in problems[0] and "(1055 m)" in problems[0]
    assert "Vmax on the dam sheet (80.8 hm³)" in problems[1] and "(90.57 hm³)" in problems[1]


def test_u_m4_01_a_surface_area_above_the_drainage_area_is_a_warning():
    curve = _curve()  # A(Hmax) = 3 km2

    assert curve_warnings(curve, 3.0) == [] and curve_warnings(curve, None) == []
    warnings = curve_warnings(curve, 2.9)

    assert len(warnings) == 1 and "3.00 km²" in warnings[0] and "2.9 km²" in warnings[0]


# --- U-M4-02: the curve -----------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"case{int(case['Case'])}")
def test_u_m4_02_the_curve_matches_the_hand_calculation(case):
    curve = _curve(int(case["Case"]))

    assert curve.dead_vol_hm3 == pytest.approx(case["Vdead_hm3"], rel=1e-12)
    assert curve.h_min_m == pytest.approx(case["Hmin_m"], rel=1e-12)
    assert curve.volume(case["Hmax_m"]) == pytest.approx(case["V_Hmax_hm3"], rel=1e-12)
    assert curve.area(case["Hmax_m"]) == pytest.approx(case["Area_Hmax_km2"], rel=1e-12)


@pytest.mark.parametrize("point", POINTS, ids=lambda point: f"case{int(point['Case'])}-{point['Point']}")
def test_u_m4_02_volume_area_and_the_inverse_match_the_hand_calculation(point):
    curve = _curve(int(point["Case"]))

    assert curve.volume(point["H_m"]) == pytest.approx(point["V_hm3"], rel=1e-12, abs=1e-12)
    assert curve.area(point["H_m"]) == pytest.approx(point["A_km2"], rel=1e-12, abs=1e-12)
    assert curve.elevation(point["V_hm3"]) == pytest.approx(point["H_m"], rel=1e-12)


def test_u_m4_02_hmin_is_the_level_of_the_dead_volume_and_hbed_the_first_level():
    curve = _curve()

    assert curve.h_min_m == 110.0 and curve.volume(curve.h_min_m) == curve.dead_vol_hm3 == 10.0
    assert curve.bed_elev_m == 100.0


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
