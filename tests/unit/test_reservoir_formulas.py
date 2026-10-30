"""U-M4-01 to U-M4-03: the reservoir curve of B3.3 against the hand calculations in tests/verification/."""

import math

import numpy as np
import pytest

from src.core.reservoir import SHAPE_CLASSES, check_inputs, check_step, curve_table, curve_warnings, fit_curve
from tests.oracle import reservoir_cases, reservoir_points

CASES = reservoir_cases()
POINTS = reservoir_points()


def _fit_arguments(case):
    return {
        "bed_elev_m": case["Hbed_m"],
        "max_elev_m": case["Hmax_m"],
        "crest_elev_m": case["Hcrest_m"],
        "active_vol_hm3": case["Vactive_hm3"],
        "max_vol_hm3": case["Vmax_hm3"],
        "h_min_m": None if case["Hmin_given_m"] == "" else case["Hmin_given_m"],
        "shape_class": case["Shape_Class"] or None,
    }


def _case(number):
    return next(case for case in CASES if case["Case"] == number)


def _fit(number):
    return fit_curve(**_fit_arguments(_case(number)))


def _valid(**changes):
    """Inputs that pass every rule of FR-M4-01, with `changes` applied."""
    values = {
        "bed_elev_m": 100.0,
        "h_min_m": 125.0,
        "max_elev_m": 150.0,
        "crest_elev_m": 155.0,
        "active_vol_hm3": 75.0,
        "max_vol_hm3": 100.0,
    }
    return {**values, **changes}


# --- U-M4-01: the inputs ----------------------------------------------------------------------


def test_u_m4_01_valid_inputs_have_no_problems():
    assert check_inputs(**_valid()) == []


def test_u_m4_01_hmin_may_be_empty_and_hmax_may_equal_the_crest():
    assert check_inputs(**_valid(h_min_m=None, crest_elev_m=150.0)) == []


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"h_min_m": 100.0}, "Hmin"),  # not above the bed
        ({"h_min_m": 90.0}, "Hmin"),
        ({"h_min_m": 150.0}, "Hmin"),  # not below Hmax
        ({"max_elev_m": 100.0, "h_min_m": None}, "Hmax"),  # not above the bed
        ({"crest_elev_m": 149.0}, "Hcrest"),  # below Hmax
        ({"active_vol_hm3": 0.0}, "Vactive"),
        ({"active_vol_hm3": -1.0}, "Vactive"),
        ({"active_vol_hm3": 100.0}, "Vactive"),  # equal to Vmax
        ({"active_vol_hm3": 120.0}, "Vactive"),
        ({"bed_elev_m": float("nan")}, "Hbed"),
        ({"max_vol_hm3": float("inf")}, "Vmax"),
    ],
)
def test_u_m4_01_each_rule_is_checked_and_named(changes, expected):
    problems = check_inputs(**_valid(**changes))

    assert problems and any(expected in problem for problem in problems)


def test_u_m4_01_every_problem_is_listed_at_once():
    problems = check_inputs(**_valid(h_min_m=90.0, crest_elev_m=149.0, active_vol_hm3=120.0))

    assert len(problems) == 3


def test_u_m4_01_a_curve_cannot_be_fitted_to_invalid_inputs():
    with pytest.raises(ValueError, match="Hmin.*\n.*Vactive"):
        fit_curve(**_fit_arguments(_case(6)) | {"h_min_m": 90.0, "active_vol_hm3": 120.0})


def test_u_m4_01_hmin_or_a_shape_class_is_needed():
    with pytest.raises(ValueError, match="Hmin or a shape class"):
        fit_curve(**_fit_arguments(_case(1)) | {"shape_class": None})


def test_u_m4_01_an_unknown_shape_class_is_refused():
    with pytest.raises(ValueError, match="mountain"):
        fit_curve(**_fit_arguments(_case(1)) | {"shape_class": "mountain"})


def test_u_m4_01_the_shape_classes_are_the_exponents_of_d19():
    assert SHAPE_CLASSES == {"gorge": 1.25, "hill": 2.0, "foothill": 3.0, "lake": 4.0}


def test_u_m4_01_the_sample_dams_give_no_warnings_but_cubuk_2_is_shallow():
    assert curve_warnings(_fit(1), 309.2) == [] and curve_warnings(_fit(2), 834.7) == []
    warnings = curve_warnings(_fit(3), 180.2)  # OI-01: Hmax is 5.3 m above the bed

    assert len(warnings) == 1 and "5.3 m" in warnings[0]


@pytest.mark.parametrize(
    ("h_min", "expected"),
    [(39.810717055349734, "m = 5.00"), (0.01, "m = 0.50")],  # Hbed 0, Hmax 100, Vmax 100, Vdead 1
)
def test_u_m4_01_a_fitted_exponent_outside_1_to_4_5_is_a_warning(h_min, expected):
    curve = fit_curve(
        bed_elev_m=0.0, max_elev_m=100.0, crest_elev_m=100.0, active_vol_hm3=99.0, max_vol_hm3=100.0, h_min_m=h_min
    )

    warnings = curve_warnings(curve)

    assert len(warnings) == 1 and expected in warnings[0] and "1 to 4.5" in warnings[0]


@pytest.mark.parametrize(("h_min", "exponent"), [(25.0, 1.0), (50.0, 2.0), (100.0 * 0.25 ** (1 / 4.4), 4.4)])
def test_u_m4_01_an_exponent_inside_1_to_4_5_is_not_a_warning(h_min, exponent):
    # Hbed 0, Hmax 100, Vmax 100, Vdead 25: Hmin = 100 * 0.25**(1/m)
    curve = fit_curve(
        bed_elev_m=0.0, max_elev_m=100.0, crest_elev_m=100.0, active_vol_hm3=75.0, max_vol_hm3=100.0, h_min_m=h_min
    )

    assert curve.exponent == pytest.approx(exponent) and curve_warnings(curve) == []


def test_u_m4_01_a_shallow_reservoir_is_a_warning():
    curve = fit_curve(
        bed_elev_m=100.0, max_elev_m=109.0, crest_elev_m=110.0, active_vol_hm3=9.0, max_vol_hm3=10.0, shape_class="hill"
    )

    warnings = curve_warnings(curve)

    assert len(warnings) == 1 and "9.0 m" in warnings[0] and "10 m" in warnings[0]
    ten = fit_curve(
        bed_elev_m=100.0, max_elev_m=110.0, crest_elev_m=110.0, active_vol_hm3=9.0, max_vol_hm3=10.0, shape_class="hill"
    )
    assert curve_warnings(ten) == []


def test_u_m4_01_a_surface_area_above_the_drainage_area_is_a_warning():
    curve = _fit(1)  # A(Hmax) = 4.09 km2

    assert curve_warnings(curve, 4.1) == []
    warnings = curve_warnings(curve, 4.0)

    assert len(warnings) == 1 and "4.09 km²" in warnings[0] and "4 km²" in warnings[0]
    assert curve_warnings(curve, None) == []  # a sheet without a drainage area has nothing to compare


# --- U-M4-02: the curve -----------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"case{int(case['Case'])}")
def test_u_m4_02_the_fit_matches_the_hand_calculation(case):
    curve = fit_curve(**_fit_arguments(case))

    assert curve.dead_vol_hm3 == pytest.approx(case["Vdead_hm3"], rel=1e-9)
    assert curve.exponent == pytest.approx(case["m"], rel=1e-9)
    assert curve.h_min_m == pytest.approx(case["Hmin_m"], rel=1e-12)
    assert curve.area(case["Hmax_m"]) == pytest.approx(case["Area_Hmax_km2"], rel=1e-9)


def test_u_m4_02_the_worked_examples_of_b3_3():
    kavsakkaya, cubuk_1, cubuk_2 = _fit(1), _fit(2), _fit(3)

    assert kavsakkaya.h_min_m == pytest.approx(1088.86, abs=0.005)
    assert kavsakkaya.area(kavsakkaya.max_elev_m) == pytest.approx(4.09, abs=0.005)
    assert cubuk_1.h_min_m == pytest.approx(892.69, abs=0.005)
    assert cubuk_1.area(cubuk_1.max_elev_m) == pytest.approx(0.57, abs=0.005)
    assert cubuk_2.area(cubuk_2.max_elev_m) == pytest.approx(8.45, abs=0.005)


@pytest.mark.parametrize("point", POINTS, ids=lambda point: f"case{int(point['Case'])}-{point['Point']}")
def test_u_m4_02_volume_area_and_the_inverse_match_the_hand_calculation(point):
    curve = _fit(int(point["Case"]))

    assert curve.volume(point["H_m"]) == pytest.approx(point["V_hm3"], rel=1e-9, abs=1e-12)
    assert curve.area(point["H_m"]) == pytest.approx(point["A_km2"], rel=1e-9, abs=1e-12)
    assert curve.elevation(point["V_hm3"]) == pytest.approx(point["H_m"], rel=1e-12)


@pytest.mark.parametrize("number", [4, 5, 6])
def test_u_m4_02_a_given_hmin_puts_the_curve_through_the_dead_volume(number):
    curve = _fit(number)
    case = _case(number)

    assert curve.volume(case["Hbed_m"]) == 0.0
    assert curve.volume(case["Hmax_m"]) == pytest.approx(case["Vmax_hm3"], rel=1e-12)
    assert curve.volume(case["Hmin_given_m"]) == pytest.approx(case["Vmax_hm3"] - case["Vactive_hm3"], rel=1e-12)


@pytest.mark.parametrize("number", [1, 2, 3, 7, 8])
def test_u_m4_02_a_shape_class_puts_the_curve_through_the_bed_and_hmax_and_hmin_is_the_inverse_of_the_dead_volume(
    number,
):
    curve = _fit(number)
    case = _case(number)

    assert curve.exponent == SHAPE_CLASSES[case["Shape_Class"]]
    assert curve.volume(case["Hbed_m"]) == 0.0
    assert curve.volume(case["Hmax_m"]) == pytest.approx(case["Vmax_hm3"], rel=1e-12)
    assert curve.volume(curve.h_min_m) == pytest.approx(curve.dead_vol_hm3, rel=1e-12)


def test_u_m4_02_the_given_hmin_wins_over_the_shape_class():
    curve = fit_curve(**_fit_arguments(_case(4)) | {"shape_class": "lake"})

    assert curve.exponent == pytest.approx(_case(4)["m"], rel=1e-12)


def test_u_m4_02_the_area_is_the_slope_of_the_volume():
    curve = _fit(1)
    for h in (1070.0, 1088.86, 1100.0, 1122.3):
        step = 1e-4
        slope = (curve.volume(h + step) - curve.volume(h - step)) / (2 * step)
        assert curve.area(h) == pytest.approx(slope, rel=1e-6)


def test_u_m4_02_the_curve_rises_and_is_empty_at_and_below_the_bed():
    curve = _fit(2)
    levels = np.linspace(888.0, 908.6, 50)

    volumes = curve.volume(levels)

    assert np.all(np.diff(volumes) > 0) and volumes[0] == 0.0
    assert curve.volume(880.0) == 0.0
    assert curve.elevation(0.0) == curve.bed_elev_m


def test_u_m4_02_the_curve_takes_arrays_and_numbers():
    curve = _fit(1)

    assert isinstance(curve.volume(1100.0), float)
    assert curve.volume(np.array([1063.0, 1122.3])) == pytest.approx([0.0, 80.8])
    assert math.isclose(float(curve.elevation(np.array([80.8]))[0]), 1122.3)


# --- U-M4-03: the table -----------------------------------------------------------------------


def test_u_m4_03_the_table_steps_half_a_metre_from_the_bed_to_the_crest():
    table = curve_table(_fit(1))  # 1063 m to 1124 m

    assert list(table.columns) == ["Elevation_m", "Volume_hm3", "Area_km2"]
    assert len(table) == 123
    assert table["Elevation_m"].iloc[0] == 1063.0 and table["Elevation_m"].iloc[-1] == 1124.0
    assert np.allclose(np.diff(table["Elevation_m"]), 0.5)
    assert table["Volume_hm3"].iloc[0] == 0.0 and table["Area_km2"].iloc[0] == 0.0


def test_u_m4_03_a_crest_off_the_grid_closes_the_table():
    table = curve_table(_fit(2))  # 888 m to 908.6 m

    elevations = table["Elevation_m"]
    assert len(table) == 43
    assert elevations.iloc[-2] == 908.5 and elevations.iloc[-1] == 908.6
    assert table["Volume_hm3"].iloc[-1] == pytest.approx(_fit(2).volume(908.6), rel=1e-12)


def test_u_m4_03_the_table_agrees_with_the_hand_calculation_on_its_grid():
    table = curve_table(_fit(6)).set_index("Elevation_m")  # 100 m to 155 m: every level of the case is on the grid

    for point in POINTS:
        if point["Case"] == 6:
            row = table.loc[point["H_m"]]
            assert row["Volume_hm3"] == pytest.approx(point["V_hm3"], rel=1e-9, abs=1e-12)
            assert row["Area_km2"] == pytest.approx(point["A_km2"], rel=1e-9, abs=1e-12)


def test_u_m4_03_the_table_rises_to_the_crest():
    table = curve_table(_fit(3))

    assert table["Volume_hm3"].is_monotonic_increasing and table["Area_km2"].is_monotonic_increasing
    assert table["Volume_hm3"].iloc[-1] > 22.4  # the curve goes on above Hmax up to the crest


def test_u_m4_03_the_table_steps_by_the_entered_interval():
    curve = _fit(1)  # 1063 m to 1124 m: 244 steps of 0.25 m

    table = curve_table(curve, 0.25)

    assert len(table) == 245
    assert table["Elevation_m"].iloc[0] == 1063.0 and table["Elevation_m"].iloc[-1] == 1124.0
    assert np.allclose(np.diff(table["Elevation_m"]), 0.25)
    assert table["Volume_hm3"].iloc[100] == pytest.approx(curve.volume(1063.0 + 100 * 0.25), rel=1e-12)


def test_u_m4_03_an_interval_off_the_crest_closes_the_table_at_the_crest():
    table = curve_table(_fit(2), 0.3)  # 888 m to 908.6 m: the last step is 908.4 m, then the crest

    elevations = table["Elevation_m"]
    assert len(table) == 70
    assert elevations.iloc[-2] == pytest.approx(908.4) and elevations.iloc[-1] == 908.6


def test_u_m4_03_an_interval_longer_than_the_depth_gives_the_bed_and_the_crest_only():
    table = curve_table(_fit(1), 100.0)

    assert list(table["Elevation_m"]) == [1063.0, 1124.0]


@pytest.mark.parametrize("step", [0.0, -0.5, float("nan"), float("inf")])
def test_u_m4_03_an_interval_must_be_a_finite_number_above_zero(step):
    with pytest.raises(ValueError, match="level interval"):
        curve_table(_fit(1), step)

    assert len(check_step(step)) == 1


def test_u_m4_03_a_positive_finite_interval_has_no_problems():
    assert check_step(0.25) == [] and check_step(0.5) == []


def test_u_m4_02_a_level_interval_that_makes_an_unusable_table_is_refused():
    with pytest.raises(ValueError, match="at most 100,000"):
        curve_table(_fit(1), 0.0001)  # 1063 m to 1124 m
