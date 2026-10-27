"""U-M5-01: the years of the minimum and maximum total volume (FR-M5-01)."""

import numpy as np
import pytest

from src.core.integration import Extreme, extremes


def test_u_m5_01_the_minimum_and_maximum_years_carry_their_total_and_elevation():
    years = [2001, 2002, 2003, 2004]
    totals = [0.30, 0.10, 0.50, 0.20]
    elevations = [901.0, 900.5, 903.0, 900.9]

    lowest, highest = extremes(years, totals, elevations)

    assert lowest == Extreme(2002, 0.10, 900.5)
    assert highest == Extreme(2003, 0.50, 903.0)


def test_u_m5_01_ties_resolve_to_the_earliest_year():
    years = [2001, 2002, 2003, 2004, 2005]
    totals = [0.20, 0.10, 0.50, 0.10, 0.50]
    elevations = [1.0, 2.0, 3.0, 4.0, 5.0]

    lowest, highest = extremes(years, totals, elevations)

    assert (lowest.year, lowest.elevation_m) == (2002, 2.0)
    assert (highest.year, highest.elevation_m) == (2003, 3.0)


def test_u_m5_01_ties_resolve_to_the_earliest_year_even_when_the_years_are_not_in_order():
    lowest, highest = extremes([2005, 2003, 2004], [0.10, 0.10, 0.50], [1.0, 2.0, 3.0])

    assert lowest.year == 2003 and highest.year == 2004


def test_u_m5_01_one_year_is_both_the_minimum_and_the_maximum():
    lowest, highest = extremes([1990], [0.25], [880.0])

    assert lowest == highest == Extreme(1990, 0.25, 880.0)


def test_u_m5_01_the_values_are_plain_numbers():
    lowest, _ = extremes(np.array([1974, 1975]), np.array([0.3, 0.2]), np.array([10.0, 11.0]))

    assert type(lowest.year) is int and type(lowest.total_hm3) is float and type(lowest.elevation_m) is float


def test_u_m5_01_an_empty_record_is_refused():
    with pytest.raises(ValueError, match="no years"):
        extremes([], [], [])
